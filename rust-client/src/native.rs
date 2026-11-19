//! Source-only C ABI to pinned Luau, with Rust-owned codec callbacks.
use std::{
    ffi::{c_char, c_void},
    ptr, slice,
};

unsafe extern "C" {
    fn local_luau_source(
        source: *const u8,
        source_len: usize,
        arguments: *const f64,
        argument_count: usize,
        snapshot: *const u8,
        snapshot_len: usize,
        timeout_ms: i32,
        memory_mb: i32,
        output: *mut *mut c_char,
        output_len: *mut usize,
        codec: unsafe extern "C" fn(u32, *const u8, usize, *mut *mut u8, *mut usize, i32) -> i32,
        release: unsafe extern "C" fn(*mut u8, usize),
    ) -> i32;
    fn local_luau_free(output: *mut c_char);
    fn local_luau_session_request(
        handle: *mut *mut c_void,
        input: *const u8,
        length: usize,
        output: *mut *mut c_char,
        output_len: *mut usize,
        codec: unsafe extern "C" fn(u32, *const u8, usize, *mut *mut u8, *mut usize, i32) -> i32,
        release: unsafe extern "C" fn(*mut u8, usize),
    ) -> i32;
    fn local_luau_session_close(handle: *mut c_void);
}

pub struct Session {
    handle: *mut c_void,
}
impl Session {
    pub fn new() -> Self {
        Self {
            handle: ptr::null_mut(),
        }
    }
    pub fn request(&mut self, input: &[u8]) -> Result<Vec<u8>, String> {
        let mut output = ptr::null_mut();
        let mut length = 0;
        // SAFETY: the opaque VM is created and used on this one worker thread.
        // Inputs remain live through the call; successful outputs are owned
        // native allocations and use the matching native release function.
        let status = unsafe {
            local_luau_session_request(
                &mut self.handle,
                input.as_ptr(),
                input.len(),
                &mut output,
                &mut length,
                crate::codecs::apply,
                crate::codecs::release,
            )
        };
        if status != 0 || output.is_null() {
            return Err("persistent native worker failed".into());
        }
        let result = if length <= 8 * 1024 * 1024 {
            Ok(unsafe { slice::from_raw_parts(output.cast::<u8>(), length) }.to_vec())
        } else {
            Err("persistent response exceeds 8 MiB".into())
        };
        unsafe { local_luau_free(output) };
        result
    }
}
impl Drop for Session {
    fn drop(&mut self) {
        if !self.handle.is_null() {
            unsafe { local_luau_session_close(self.handle) };
            self.handle = ptr::null_mut();
        }
    }
}

pub fn run(
    source: &[u8],
    arguments: &[f64],
    snapshot: Option<&[u8]>,
    timeout_ms: u32,
    memory_mb: u32,
) -> Result<Vec<u8>, String> {
    let mut output = ptr::null_mut();
    let mut length = 0;
    // SAFETY: every pointer refers to a slice live for the entire synchronous
    // call. Native code copies inputs, catches exceptions, and bounds output.
    let status = unsafe {
        local_luau_source(
            source.as_ptr(),
            source.len(),
            arguments.as_ptr(),
            arguments.len(),
            snapshot.map_or(ptr::null(), |v| v.as_ptr()),
            snapshot.map_or(0, |v| v.len()),
            timeout_ms as i32,
            memory_mb as i32,
            &mut output,
            &mut length,
            crate::codecs::apply,
            crate::codecs::release,
        )
    };
    if status != 0 {
        return Err("native source worker failed".into());
    }
    if output.is_null() {
        return Err("native worker returned no allocation".into());
    }
    // SAFETY: successful native calls return a malloc allocation of exactly
    // length bytes. Copy it before returning it to the matching native free.
    let data = if length <= 8 * 1024 * 1024 {
        Ok(unsafe { slice::from_raw_parts(output.cast::<u8>(), length) }.to_vec())
    } else {
        Err("native result exceeds 8 MiB".into())
    };
    unsafe { local_luau_free(output) };
    data
}
