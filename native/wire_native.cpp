// Native replacement for the hot part of scripts/world_replication.py: World.property_list / World.value.
//
// The Python decoder spends most of its time in millions of tiny Reader calls (struct.unpack per field). This extension decodes a
// whole property list in one call and builds the same Python objects the Python code builds. It is deliberately conservative:
// anything it does not handle exactly (a malformed stream, a rare property type, a limit violation) raises Fallback, and the
// Python caller then re-decodes the same bytes with the Python implementation, which also produces the original error messages.
// So the extension can only make successful decodes faster; it never changes what is accepted or what is returned.
//
// Built against the stable ABI (Py_LIMITED_API), so one build works for any Python >= 3.11:
//   python scripts/build_native_wire.py
#define PY_SSIZE_T_CLEAN
#ifndef Py_LIMITED_API
#define Py_LIMITED_API 0x030B0000
#endif
#include <Python.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

PyObject* g_fallback = nullptr;  // _wire_native.Fallback

namespace {

struct Fallback {};  // thrown for anything the Python implementation must handle

// Owning reference to a Python object; releases it when an exception unwinds.
struct Obj {
    PyObject* p = nullptr;
    Obj() = default;
    explicit Obj(PyObject* object) : p(object) { if (!p) throw Fallback{}; }
    Obj(const Obj&) = delete;
    Obj& operator=(const Obj&) = delete;
    Obj(Obj&& other) noexcept : p(other.p) { other.p = nullptr; }
    Obj& operator=(Obj&& other) noexcept { if (this != &other) { Py_XDECREF(p); p = other.p; other.p = nullptr; } return *this; }
    ~Obj() { Py_XDECREF(p); }
    PyObject* release() { PyObject* out = p; p = nullptr; return out; }
};

Obj make_int(long long value) { return Obj(PyLong_FromLongLong(value)); }
Obj make_uint(unsigned long long value) { return Obj(PyLong_FromUnsignedLongLong(value)); }
Obj make_float(double value) { return Obj(PyFloat_FromDouble(value)); }
Obj make_bytes(const uint8_t* data, size_t size) { return Obj(PyBytes_FromStringAndSize(reinterpret_cast<const char*>(data), static_cast<Py_ssize_t>(size))); }
Obj make_hex(const uint8_t* data, size_t size) {
    static const char digits[] = "0123456789abcdef";
    std::string text(size * 2, '0');
    for (size_t i = 0; i < size; ++i) { text[2 * i] = digits[data[i] >> 4]; text[2 * i + 1] = digits[data[i] & 15]; }
    return Obj(PyUnicode_FromStringAndSize(text.data(), static_cast<Py_ssize_t>(text.size())));
}
Obj make_none() { Py_INCREF(Py_None); return Obj(Py_None); }
Obj make_bool(bool value) { PyObject* out = value ? Py_True : Py_False; Py_INCREF(out); return Obj(out); }
Obj make_list(size_t size) { return Obj(PyList_New(static_cast<Py_ssize_t>(size))); }
void list_set(Obj& list, size_t index, Obj&& item) {
    if (PyList_SetItem(list.p, static_cast<Py_ssize_t>(index), item.release()) != 0) throw Fallback{};
}
Obj make_tuple2(Obj&& a, Obj&& b) {
    Obj tuple(PyTuple_New(2));
    if (PyTuple_SetItem(tuple.p, 0, a.release()) != 0) throw Fallback{};
    if (PyTuple_SetItem(tuple.p, 1, b.release()) != 0) throw Fallback{};
    return tuple;
}
Obj make_dict() { return Obj(PyDict_New()); }
void dict_set(Obj& dict, const char* key, Obj&& value) {
    if (PyDict_SetItemString(dict.p, key, value.p) != 0) throw Fallback{};
}

struct Schema {
    PyObject* names = nullptr;    // schema['names']: list of str
    PyObject* strings = nullptr;  // schema['strings']: list of str
    PyObject* shared = nullptr;   // dict of known shared-string keys
    PyObject* deferred = nullptr; // set that receives unknown shared-string keys
};

class Decoder {
public:
    Decoder(const uint8_t* data, size_t size, size_t pos, const Schema& schema) : data_(data), size_(size), pos_(pos), schema_(schema) {}
    size_t pos() const { return pos_; }

    uint8_t u8() { need(1); return data_[pos_++]; }
    uint16_t u16() { need(2); uint16_t v; std::memcpy(&v, data_ + pos_, 2); pos_ += 2; return v; }
    uint32_t u32() { need(4); uint32_t v; std::memcpy(&v, data_ + pos_, 4); pos_ += 4; return v; }
    uint64_t u64() { need(8); uint64_t v; std::memcpy(&v, data_ + pos_, 8); pos_ += 8; return v; }
    int32_t i32() { return static_cast<int32_t>(u32()); }
    int64_t i64() { return static_cast<int64_t>(u64()); }
    double f32() { need(4); float v; std::memcpy(&v, data_ + pos_, 4); pos_ += 4; return static_cast<double>(v); }
    double f64() { need(8); double v; std::memcpy(&v, data_ + pos_, 8); pos_ += 8; return v; }
    const uint8_t* take(size_t size) { need(size); const uint8_t* out = data_ + pos_; pos_ += size; return out; }

    // Reader.varuint(bits): at most ceil(bits / 7) bytes; the value must fit in `bits`.
    uint64_t varuint(int bits = 32) {
        uint64_t value = 0;
        for (int shift = 0; shift < bits; shift += 7) {
            const uint8_t part = u8();
            const uint64_t chunk = part & 127;
            if (shift >= 64 || (shift > 0 && chunk > (UINT64_MAX >> shift))) throw Fallback{};  // would not fit in 64 bits
            value |= chunk << shift;
            if (!(part & 128)) {
                if (bits < 64 && value >= (uint64_t(1) << bits)) throw Fallback{};
                return value;
            }
        }
        throw Fallback{};
    }
    int64_t signed_varint(int bits) {
        const uint64_t value = varuint(bits);
        return static_cast<int64_t>(value >> 1) ^ -static_cast<int64_t>(value & 1);
    }
    size_t count(uint64_t limit = 65535) {
        const uint64_t value = varuint(32);
        if (value > limit) throw Fallback{};
        return static_cast<size_t>(value);
    }

    // World.value(r, p, deferred, depth, compressed): one property value of wire type `t`.
    Obj value(int t, int depth, bool compressed) {
        if (depth > 16) throw Fallback{};
        switch (t) {
            case 2: case 8: { const size_t n = count(16 * 1024 * 1024); return make_bytes(take(n), n); }
            case 33: return content_id(compressed);
            case 0: case 3: return make_none();
            case 29: case 30: {
                const size_t n = count(10000);
                Obj list = make_list(n);
                for (size_t i = 0; i < n; ++i) list_set(list, i, variant(depth + 1, compressed));
                return list;
            }
            case 31: case 32: {
                const size_t n = count(10000);
                Obj list = make_list(n);
                for (size_t i = 0; i < n; ++i) {
                    const size_t size = count();
                    Obj key = make_bytes(take(size), size);
                    list_set(list, i, make_tuple2(std::move(key), variant(depth + 1, compressed)));
                }
                return list;
            }
            case 7: return make_uint(varuint(32));
            case 18: return make_int(u16());
            case 9: { const uint8_t v = u8(); if (v > 1) throw Fallback{}; return make_bool(v != 0); }
            case 10: return make_int(signed_varint(32));
            case 11: return make_float(f32());
            case 12: return make_float(f64());
            case 48: {
                const int64_t millis = i64();
                if (millis < -17987443200000LL || millis > 253402300799999LL) throw Fallback{};
                Obj dict = make_dict();
                dict_set(dict, "$datetime", make_int(millis));
                return dict;
            }
            case 13: { Obj list = make_list(2); const double a = f32(); const int32_t b = i32(); list_set(list, 0, make_float(a)); list_set(list, 1, make_int(b)); return list; }
            case 14: {
                Obj list = make_list(4);
                const double a = f32(); const int32_t b = i32(); const double c = f32(); const int32_t d = i32();
                list_set(list, 0, make_float(a)); list_set(list, 1, make_int(b)); list_set(list, 2, make_float(c)); list_set(list, 3, make_int(d));
                return list;
            }
            case 21: case 37: return floats(2);
            case 40: return floats(4);
            case 19: case 22: case 36: return floats(3);
            case 20: { Obj list = make_list(3); const uint8_t* b = take(3); for (size_t i = 0; i < 3; ++i) list_set(list, i, make_int(b[i])); return list; }
            case 27: {
                Obj position = floats(3);
                const uint8_t rotation = u8();
                Obj dict = make_dict();
                dict_set(dict, "position", std::move(position));
                dict_set(dict, "rotation_id", make_int(rotation));
                if (rotation == 0) { const uint8_t* b = take(6); dict_set(dict, "packed_rotation", make_hex(b, 6)); }
                else dict_set(dict, "packed_rotation", make_none());
                return dict;
            }
            case 41: {
                const uint8_t flag = u8();
                if (!(flag & 1)) return make_none();
                return floats(flag >= 2 ? 6 : 5);
            }
            case 51: {
                const uint8_t flag = u8();
                if (!(flag & 128)) return make_none();
                Obj rotation;
                if (flag == 128) { const uint8_t* b = take(6); rotation = make_hex(b, 6); }
                else rotation = make_int(flag & 127);
                Obj position = floats(3);
                Obj dict = make_dict();
                dict_set(dict, "rotation", std::move(rotation));
                dict_set(dict, "position", std::move(position));
                return dict;
            }
            case 54: {
                Obj list = make_list(4);
                list_set(list, 0, make_int(u16()));
                list_set(list, 1, make_int(u8()));
                { const size_t n = u32(); list_set(list, 2, make_bytes(take(n), n)); }
                { const size_t n = u32(); list_set(list, 3, make_bytes(take(n), n)); }
                return list;
            }
            case 60: {
                const uint64_t identity = u64();
                const uint64_t index = varuint(32);
                const uint64_t type_word = u64();
                Obj inner = make_dict();
                dict_set(inner, "identity", make_uint(identity));
                dict_set(inner, "index", make_uint(index));
                dict_set(inner, "type_word", make_uint(type_word));
                Obj outer = make_dict();
                dict_set(outer, "lr_reference", std::move(inner));
                return outer;
            }
            case 61: {
                const uint64_t marker = varuint(32);
                if (marker == 0) return make_none();
                if (marker == 1) return content_id(compressed);
                throw Fallback{};
            }
            case 28: case 69: return guid();
            case 34: return make_uint(varuint(32));
            case 35: case 38: {
                const uint32_t n = u32();
                if (n > 20) throw Fallback{};
                Obj list = make_list(n);
                for (uint32_t i = 0; i < n; ++i) list_set(list, i, floats(t == 35 ? 3 : 5));
                return list;
            }
            case 57: return packed_pv();
            case 44: return make_int(signed_varint(64));
            case 68: {
                Obj list = make_list(4);
                list_set(list, 0, make_int(signed_varint(64)));
                list_set(list, 1, make_uint(varuint(32)));
                list_set(list, 2, make_int(signed_varint(64)));
                list_set(list, 3, make_int(signed_varint(64)));
                return list;
            }
            case 52: case 55: return make_uint(u64());
            case 46: case 47: {
                const uint8_t* key = take(16);
                Obj bytes = make_bytes(key, 16);
                const int known = PyDict_Contains(schema_.shared, bytes.p);
                if (known < 0) throw Fallback{};
                if (!known && PySet_Add(schema_.deferred, bytes.p) != 0) throw Fallback{};
                Obj dict = make_dict();
                dict_set(dict, "shared", make_hex(key, 16));
                return dict;
            }
            case 49: {
                const uint8_t marker = u8();
                if (marker & 128) {
                    size_t index = marker & 127;
                    if (index == 127) index += static_cast<size_t>(varuint(32));
                    return schema_string(schema_.names, index);
                }
                const size_t size = marker == 127 ? count() : marker;
                return make_bytes(take(size), size);
            }
            default: throw Fallback{};  // 56 (zstd buffer), 65-67 (animation tracks) and anything unknown stay in Python
        }
    }

private:
    void need(size_t n) const { if (n > size_ - pos_) throw Fallback{}; }

    Obj floats(size_t n) {
        Obj list = make_list(n);
        for (size_t i = 0; i < n; ++i) list_set(list, i, make_float(f32()));
        return list;
    }
    Obj guid() {
        const uint64_t scope = varuint(32);
        if (!scope) return make_none();
        const uint32_t second = u32();
        return make_tuple2(make_uint(scope), make_uint(second));
    }
    Obj schema_string(PyObject* list, size_t index) {
        // Python: self.schema['names'][index].encode()
        if (index >= static_cast<size_t>(PyList_Size(list))) throw Fallback{};
        PyObject* item = PyList_GetItem(list, static_cast<Py_ssize_t>(index));  // borrowed
        if (!item) throw Fallback{};
        Py_ssize_t size = 0;
        const char* text = PyUnicode_AsUTF8AndSize(item, &size);
        if (!text) throw Fallback{};
        return Obj(PyBytes_FromStringAndSize(text, size));
    }
    Obj content_id(bool compressed) {
        if (!compressed) { const size_t n = count(16 * 1024 * 1024); return make_bytes(take(n), n); }
        const uint8_t marker = u8();
        const size_t index = marker >> 1;
        if (index >= static_cast<size_t>(PyList_Size(schema_.strings))) throw Fallback{};
        Obj prefix = schema_string(schema_.strings, index);
        std::string text(PyBytes_AsString(prefix.p), static_cast<size_t>(PyBytes_Size(prefix.p)));
        if (marker & 1) text += std::to_string(signed_varint(64));
        else { const size_t n = count(16 * 1024 * 1024); const uint8_t* b = take(n); text.append(reinterpret_cast<const char*>(b), n); }
        return Obj(PyBytes_FromStringAndSize(text.data(), static_cast<Py_ssize_t>(text.size())));
    }
    Obj variant(int depth, bool compressed) {
        const uint8_t type = u8();
        if (type == 7) u16();  // enum id: read and ignored, as in the Python decoder
        return value(type, depth, compressed);
    }
    // World.compact_position
    Obj compact_position() {
        auto signed32 = [](uint64_t v) -> int32_t { return static_cast<int32_t>(static_cast<uint32_t>(v & 0xffffffffu)); };
        const uint8_t b = u8();
        const uint64_t sx = (b & 4) ? 1 : 0, sy = (b & 2) ? 1 : 0, sz = (b & 1) ? 1 : 0;
        int64_t xyz[3];
        double divisor;
        if (b <= 0x27) {
            const uint64_t n = u32();
            xyz[0] = signed32((2 * n) | (sx << 31)) >> 21;
            xyz[1] = signed32(((n << 11) & 0x7fe00000u) | (sy << 31)) >> 21;
            xyz[2] = signed32((sz << 31) | ((n & 1023) << 21)) >> 21;
            divisor = 1023.0;
        } else if (b <= 0x57) {
            const uint64_t s[3] = {sx, sy, sz};
            for (int i = 0; i < 3; ++i) { const uint64_t w = u16(); xyz[i] = signed32((s[i] << 31) | (w << 15)) >> 15; }
            divisor = 65535.0;
        } else {
            const uint64_t n = u32(), m = u32();
            xyz[0] = signed32((((static_cast<uint64_t>(b >> 2) << 32) | n) >> 1)) >> 10;
            xyz[1] = signed32((sy << 31) | ((((n & 2047) << 10) | (m >> 21)) << 10)) >> 10;
            xyz[2] = signed32((sz << 31) | ((m & 0x1fffff) << 10)) >> 10;
            divisor = 2097151.0;
        }
        Obj list = make_list(3);
        for (int i = 0; i < 3; ++i) list_set(list, i, make_float(std::ldexp(static_cast<double>(xyz[i]) / divisor, b >> 3)));
        return list;
    }
    Obj packed_pv() {  // property type 57
        const uint8_t flags = u8();
        Obj position;
        if (flags & 128) { position = make_list(3); for (int i = 0; i < 3; ++i) list_set(position, i, make_float(0.0)); }
        else position = compact_position();
        const int rot = flags & 31;
        Obj rotation;
        if (rot == 31) rotation = floats(7);
        else if (rot == 0) { const uint8_t* b = take(6); rotation = make_hex(b, 6); }
        else rotation = make_int(rot);
        Obj velocities = make_list(2);
        size_t slot = 0;
        for (int mask : {64, 32}) {
            if (flags & mask) list_set(velocities, slot, make_none());
            else {
                const uint8_t b = u8();
                Obj pair = make_list(2);
                list_set(pair, 0, make_int(b));
                list_set(pair, 1, make_uint(b ? u32() : 0));
                list_set(velocities, slot, std::move(pair));
            }
            ++slot;
        }
        Obj dict = make_dict();
        dict_set(dict, "position", std::move(position));
        dict_set(dict, "rotation", std::move(rotation));
        dict_set(dict, "packed_velocities", std::move(velocities));
        dict_set(dict, "position_present", make_bool(!(flags & 128)));
        return dict;
    }

    const uint8_t* data_;
    size_t size_;
    size_t pos_;
    const Schema& schema_;
};

// property_list(data, pos, props, names, strings, shared, compressed) -> (new_pos, {name: value}, {deferred keys})
// props: sequence of (name, wire type) for the class's properties, in schema order.
PyObject* property_list(PyObject*, PyObject* args) {
    PyObject *data_obj, *props, *names, *strings, *shared;
    Py_ssize_t pos;
    int compressed;
    if (!PyArg_ParseTuple(args, "OnOOOOp", &data_obj, &pos, &props, &names, &strings, &shared, &compressed)) return nullptr;
    if (pos < 0 || !PyList_Check(names) || !PyList_Check(strings) || !PyDict_Check(shared)) {
        PyErr_SetString(g_fallback, "unexpected argument types");
        return nullptr;
    }
    Py_buffer view;
    if (PyObject_GetBuffer(data_obj, &view, PyBUF_SIMPLE) != 0) return nullptr;
    PyObject* result = nullptr;
    try {
        if (static_cast<size_t>(pos) > static_cast<size_t>(view.len)) throw Fallback{};
        const Py_ssize_t count = PySequence_Size(props);
        if (count < 0) throw Fallback{};
        struct PropertyInfo { PyObject* name; long type; };
        std::vector<PropertyInfo> infos(static_cast<size_t>(count));
        for (Py_ssize_t i = 0; i < count; ++i) {
            Obj entry(PySequence_GetItem(props, i));
            if (!PyTuple_Check(entry.p) || PyTuple_Size(entry.p) != 2) throw Fallback{};
            // Borrowed from the tuple, which `props` keeps alive for the whole call.
            infos[static_cast<size_t>(i)].name = PyTuple_GetItem(entry.p, 0);
            infos[static_cast<size_t>(i)].type = PyLong_AsLong(PyTuple_GetItem(entry.p, 1));
            if (PyErr_Occurred()) throw Fallback{};
        }
        Obj values = make_dict();
        Obj deferred(PySet_New(nullptr));
        Schema schema{names, strings, shared, deferred.p};
        Decoder decoder(static_cast<const uint8_t*>(view.buf), static_cast<size_t>(view.len), static_cast<size_t>(pos), schema);
        int last = -1;
        for (;;) {
            const int index = decoder.u8();
            if (index == 255) break;
            if (index <= last || static_cast<Py_ssize_t>(index) >= count) throw Fallback{};
            last = index;
            Obj item = decoder.value(static_cast<int>(infos[static_cast<size_t>(index)].type), 0, compressed != 0);
            if (PyDict_SetItem(values.p, infos[static_cast<size_t>(index)].name, item.p) != 0) throw Fallback{};
        }
        Obj new_pos = make_uint(decoder.pos());
        result = PyTuple_New(3);
        if (!result) throw Fallback{};
        PyTuple_SetItem(result, 0, new_pos.release());
        PyTuple_SetItem(result, 1, values.release());
        PyTuple_SetItem(result, 2, deferred.release());
    } catch (const Fallback&) {
        PyErr_Clear();
        PyBuffer_Release(&view);
        Py_XDECREF(result);
        PyErr_SetString(g_fallback, "native decoder defers to the Python implementation");
        return nullptr;
    }
    PyBuffer_Release(&view);
    return result;
}

// Deep copy of plain decoded data (dict/list/tuple/set of str/bytes/int/float/bool/None). The replication world copies every created
// instance into its action journal, and copy.deepcopy dominated that path. These structures are trees with no shared references, so a
// plain recursive copy is equivalent. Any other type raises Fallback and the caller uses copy.deepcopy.
Obj copy_tree(PyObject* o, int depth) {
    if (depth > 64) throw Fallback{};
    if (o == Py_None || PyBool_Check(o) || PyLong_CheckExact(o) || PyFloat_CheckExact(o) || PyBytes_CheckExact(o) || PyUnicode_CheckExact(o)) {
        Py_INCREF(o);
        return Obj(o);
    }
    if (PyDict_CheckExact(o)) {
        Obj out = make_dict();
        Py_ssize_t position = 0;
        PyObject *key, *value;
        while (PyDict_Next(o, &position, &key, &value)) {
            Obj k = copy_tree(key, depth + 1);
            Obj v = copy_tree(value, depth + 1);
            if (PyDict_SetItem(out.p, k.p, v.p) != 0) throw Fallback{};
        }
        return out;
    }
    if (PyList_CheckExact(o)) {
        const Py_ssize_t n = PyList_Size(o);
        Obj out = make_list(static_cast<size_t>(n));
        for (Py_ssize_t i = 0; i < n; ++i) list_set(out, static_cast<size_t>(i), copy_tree(PyList_GetItem(o, i), depth + 1));
        return out;
    }
    if (PyTuple_CheckExact(o)) {
        const Py_ssize_t n = PyTuple_Size(o);
        Obj out(PyTuple_New(n));
        for (Py_ssize_t i = 0; i < n; ++i) {
            Obj item = copy_tree(PyTuple_GetItem(o, i), depth + 1);
            if (PyTuple_SetItem(out.p, i, item.release()) != 0) throw Fallback{};
        }
        return out;
    }
    if (PyAnySet_CheckExact(o) && !PyFrozenSet_CheckExact(o)) {
        Obj out(PySet_New(nullptr));
        Obj iterator(PyObject_GetIter(o));
        while (PyObject* raw = PyIter_Next(iterator.p)) {
            Obj item(raw);
            Obj copied = copy_tree(item.p, depth + 1);
            if (PySet_Add(out.p, copied.p) != 0) throw Fallback{};
        }
        if (PyErr_Occurred()) throw Fallback{};
        return out;
    }
    throw Fallback{};
}

PyObject* copy_tree_method(PyObject*, PyObject* arg) {
    try {
        Obj copied = copy_tree(arg, 0);
        return copied.release();
    } catch (const Fallback&) {
        PyErr_Clear();
        PyErr_SetString(g_fallback, "unsupported type for the native copy");
        return nullptr;
    }
}

// scripts/world_snapshot.py _encode(value, type_id): the common cases of the decoded-value -> Luau-host JSON conversion.
// CFrame-like values, remote variants, sequences and anything unusual raise Fallback so the Python code (which also raises the
// original ValueErrors) handles them.
Obj encode_value(PyObject* value, long type_id, int depth);

Obj dict1(const char* key, Obj&& value) { Obj d = make_dict(); dict_set(d, key, std::move(value)); return d; }

Obj encode_scalar_number(PyObject* v) {
    if (PyLong_CheckExact(v)) { Py_INCREF(v); return Obj(v); }
    const double d = PyFloat_AsDouble(v);
    if (d == -1.0 && PyErr_Occurred()) throw Fallback{};
    if (std::isfinite(d)) { Py_INCREF(v); return Obj(v); }
    const char* text = std::isnan(d) ? "nan" : (d > 0 ? "inf" : "-inf");
    return dict1("$number", Obj(PyUnicode_FromString(text)));
}

Obj encode_components(PyObject* value, size_t count) {
    if (!(PyList_CheckExact(value) || PyTuple_CheckExact(value))) throw Fallback{};
    const bool is_list = PyList_CheckExact(value);
    if (static_cast<size_t>(is_list ? PyList_Size(value) : PyTuple_Size(value)) != count) throw Fallback{};
    Obj list = make_list(count);
    for (size_t i = 0; i < count; ++i) {
        PyObject* item = is_list ? PyList_GetItem(value, static_cast<Py_ssize_t>(i)) : PyTuple_GetItem(value, static_cast<Py_ssize_t>(i));
        if (!(PyLong_CheckExact(item) || PyFloat_CheckExact(item))) throw Fallback{};
        list_set(list, i, encode_scalar_number(item));
    }
    return list;
}
Obj slice_copy(PyObject* list, size_t from, size_t to) {
    Obj out = make_list(to - from);
    for (size_t i = from; i < to; ++i) {
        PyObject* item = PyList_GetItem(list, static_cast<Py_ssize_t>(i));
        Py_INCREF(item);
        list_set(out, i - from, Obj(item));
    }
    return out;
}
Obj ref_text(PyObject* a, PyObject* b) {
    Obj ra(PyObject_Str(a)), rb(PyObject_Str(b));
    return Obj(PyUnicode_FromFormat("%U:%U", ra.p, rb.p));
}

Obj encode_value(PyObject* value, long type_id, int depth) {
    if (depth > 16) throw Fallback{};
    if (PyDict_CheckExact(value) && PyDict_Size(value) == 1) {
        Obj marker(PyUnicode_FromString("$remote_variant"));
        const int has = PyDict_Contains(value, marker.p);
        if (has != 0) throw Fallback{};  // remote variants (and errors) are handled in Python
    }
    if (type_id == 28 || type_id == 69) {
        if (value == Py_None) return make_none();
        if (!PyTuple_CheckExact(value) || PyTuple_Size(value) != 2) throw Fallback{};
        PyObject *a = PyTuple_GetItem(value, 0), *b = PyTuple_GetItem(value, 1);
        if (!PyLong_CheckExact(a) || !PyLong_CheckExact(b)) throw Fallback{};
        return dict1("$ref", ref_text(a, b));
    }
    if (type_id == 18) { Py_INCREF(value); return dict1("$brickcolor", Obj(value)); }
    if (PyBytes_CheckExact(value)) {
        PyObject* decoded = PyUnicode_DecodeUTF8(PyBytes_AsString(value), PyBytes_Size(value), "strict");
        if (decoded) return Obj(decoded);
        PyErr_Clear();
        const auto* data = reinterpret_cast<const uint8_t*>(PyBytes_AsString(value));
        return dict1("$bytes_hex", make_hex(data, static_cast<size_t>(PyBytes_Size(value))));
    }
    if (value == Py_None || PyBool_Check(value) || PyUnicode_CheckExact(value) || PyLong_CheckExact(value)) { Py_INCREF(value); return Obj(value); }
    if (PyFloat_CheckExact(value)) return encode_scalar_number(value);
    switch (type_id) {
        case 13: return dict1("$udim", encode_components(value, 2));
        case 14: {
            Obj values = encode_components(value, 4);
            Obj pair = make_list(2);
            list_set(pair, 0, dict1("$udim", slice_copy(values.p, 0, 2)));
            list_set(pair, 1, dict1("$udim", slice_copy(values.p, 2, 4)));
            return dict1("$udim2", std::move(pair));
        }
        case 19: return dict1("$color3", encode_components(value, 3));
        case 20: {
            Obj raw = encode_components(value, 3);
            Obj out = make_list(3);
            for (size_t i = 0; i < 3; ++i) {
                PyObject* item = PyList_GetItem(raw.p, static_cast<Py_ssize_t>(i));
                if (!PyLong_CheckExact(item)) throw Fallback{};
                const long v = PyLong_AsLong(item);
                if (v < 0 || v > 255) throw Fallback{};
                list_set(out, i, make_float(static_cast<double>(v) / 255.0));
            }
            return dict1("$color3", std::move(out));
        }
        case 21: return dict1("$vector2", encode_components(value, 2));
        case 37: return dict1("$number_range", encode_components(value, 2));
        case 40: {
            Obj values = encode_components(value, 4);
            Obj pair = make_list(2);
            list_set(pair, 0, dict1("$vector2", slice_copy(values.p, 0, 2)));
            list_set(pair, 1, dict1("$vector2", slice_copy(values.p, 2, 4)));
            return dict1("$rect", std::move(pair));
        }
        case 22: return dict1("$vector3", encode_components(value, 3));
        case 35: case 38: throw Fallback{};
        case 27: case 51: case 57: if (PyDict_Check(value)) throw Fallback{}; break;
        default: break;
    }
    if (PyTuple_CheckExact(value) && PyTuple_Size(value) == 2 && PyLong_CheckExact(PyTuple_GetItem(value, 0)) && PyLong_CheckExact(PyTuple_GetItem(value, 1)))
        return dict1("$ref", ref_text(PyTuple_GetItem(value, 0), PyTuple_GetItem(value, 1)));
    if (PyList_CheckExact(value)) {
        const Py_ssize_t n = PyList_Size(value);
        Obj out = make_list(static_cast<size_t>(n));
        for (Py_ssize_t i = 0; i < n; ++i) list_set(out, static_cast<size_t>(i), encode_value(PyList_GetItem(value, i), -1, depth + 1));
        return out;
    }
    if (PyTuple_CheckExact(value)) {
        const Py_ssize_t n = PyTuple_Size(value);
        Obj out = make_list(static_cast<size_t>(n));
        for (Py_ssize_t i = 0; i < n; ++i) list_set(out, static_cast<size_t>(i), encode_value(PyTuple_GetItem(value, i), -1, depth + 1));
        return out;
    }
    if (PyDict_CheckExact(value)) {
        Obj out = make_dict();
        Py_ssize_t position = 0;
        PyObject *key, *item;
        while (PyDict_Next(value, &position, &key, &item)) {
            if (!PyUnicode_CheckExact(key)) throw Fallback{};
            Obj encoded = encode_value(item, -1, depth + 1);
            if (PyDict_SetItem(out.p, key, encoded.p) != 0) throw Fallback{};
        }
        return out;
    }
    throw Fallback{};
}

PyObject* encode_method(PyObject*, PyObject* args) {
    PyObject* value;
    PyObject* type_obj;
    if (!PyArg_ParseTuple(args, "OO", &value, &type_obj)) return nullptr;
    try {
        long type_id = -1;
        if (type_obj != Py_None) {
            if (!PyLong_CheckExact(type_obj)) throw Fallback{};
            type_id = PyLong_AsLong(type_obj);
            if (type_id == -1 && PyErr_Occurred()) throw Fallback{};
        }
        Obj encoded = encode_value(value, type_id, 0);
        return encoded.release();
    } catch (const Fallback&) {
        PyErr_Clear();
        PyErr_SetString(g_fallback, "encode defers to the Python implementation");
        return nullptr;
    }
}

// scripts/runtime_diagnostics.py _valid_json_value: plain JSON-ready data only (exact types, str keys, at most 64 levels). Pure
// C-API reads of exact builtin types, so no Python code runs and the answer cannot change while it walks.
bool valid_json(PyObject* value, int depth) {
    if (depth > 64) return false;
    if (value == Py_None || PyUnicode_CheckExact(value) || PyLong_CheckExact(value) || PyFloat_CheckExact(value) || PyBool_Check(value)) return true;
    if (PyList_CheckExact(value)) {
        const Py_ssize_t n = PyList_Size(value);
        for (Py_ssize_t i = 0; i < n; ++i)
            if (!valid_json(PyList_GetItem(value, i), depth + 1)) return false;
        return true;
    }
    if (PyTuple_CheckExact(value)) {
        const Py_ssize_t n = PyTuple_Size(value);
        for (Py_ssize_t i = 0; i < n; ++i)
            if (!valid_json(PyTuple_GetItem(value, i), depth + 1)) return false;
        return true;
    }
    if (PyDict_CheckExact(value)) {
        Py_ssize_t position = 0;
        PyObject *key, *item;
        while (PyDict_Next(value, &position, &key, &item))
            if (!PyUnicode_CheckExact(key) || !valid_json(item, depth + 1)) return false;
        return true;
    }
    return false;
}

PyObject* valid_json_method(PyObject*, PyObject* arg) {
    if (valid_json(arg, 0)) Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

PyMethodDef methods[] = {
    {"property_list", property_list, METH_VARARGS, "Decode one replicated property list; raises Fallback to defer to Python."},
    {"copy_tree", copy_tree_method, METH_O, "Deep copy of plain data; raises Fallback for any other type."},
    {"encode", encode_method, METH_VARARGS, "world_snapshot._encode for the common value shapes; raises Fallback otherwise."},
    {"valid_json", valid_json_method, METH_O, "runtime_diagnostics._valid_json_value: True for plain JSON-ready data."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {PyModuleDef_HEAD_INIT, "_wire_native", "Native replication decoder.", -1, methods, nullptr, nullptr, nullptr, nullptr};

}  // namespace

PyMODINIT_FUNC PyInit__wire_native(void) {
    PyObject* m = PyModule_Create(&module);
    if (!m) return nullptr;
    g_fallback = PyErr_NewException("_wire_native.Fallback", nullptr, nullptr);
    if (!g_fallback) { Py_DECREF(m); return nullptr; }
    Py_INCREF(g_fallback);
    if (PyModule_AddObject(m, "Fallback", g_fallback) != 0) { Py_DECREF(g_fallback); Py_DECREF(m); return nullptr; }
    return m;
}
