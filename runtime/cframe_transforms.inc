// Included inside world_bindings.cpp's private namespace. These operations
// use the same CFrame userdata and snapshot encoding as Instance properties.
// Public API: https://create.roblox.com/docs/reference/engine/datatypes/CFrame
using FrameVector = std::array<double, 3>;
using FrameMatrix = std::array<double, 9>;

CFrameValue* checked_cframe(lua_State* L, int index, bool require_rotation = true) {
    auto* value = static_cast<CFrameValue*>(luaL_checkudata(L, index, kCFrameMeta));
    if (require_rotation && !value->rotation_known)
        luaL_error(L, "CFrame rotation metadata is unavailable");
    return value;
}

FrameVector checked_frame_vector(lua_State* L, int index) {
    const auto* value = luaL_checkvector(L, index);
    return {double(value[0]), double(value[1]), double(value[2])};
}

double finite_frame_angle(lua_State* L, int index) {
    double value = luaL_checknumber(L, index);
    if (!std::isfinite(value)) luaL_error(L, "CFrame angle must be finite");
    return value;
}

FrameVector frame_rotate(const FrameMatrix& r, const FrameVector& p) {
    return {r[0]*p[0] + r[1]*p[1] + r[2]*p[2],
            r[3]*p[0] + r[4]*p[1] + r[5]*p[2],
            r[6]*p[0] + r[7]*p[1] + r[8]*p[2]};
}

FrameMatrix frame_product(const FrameMatrix& a, const FrameMatrix& b) {
    FrameMatrix result{};
    for (int row = 0; row < 3; ++row)
        for (int col = 0; col < 3; ++col)
            for (int k = 0; k < 3; ++k)
                result[3*row+col] += a[3*row+k]*b[3*k+col];
    return result;
}

int push_frame_value(lua_State* L, const FrameVector& p, const FrameMatrix& r) {
    auto* value = new_cframe(L);
    value->p = p;
    value->r = r;
    luaL_getmetatable(L, kCFrameMeta);
    lua_setmetatable(L, -2);
    return 1;
}

void frame_inverse_parts(const CFrameValue& value, FrameVector& p, FrameMatrix& r) {
    // CFrames contain rotation matrices: their inverse rotation is a transpose.
    r = {value.r[0], value.r[3], value.r[6],
         value.r[1], value.r[4], value.r[7],
         value.r[2], value.r[5], value.r[8]};
    p = frame_rotate(r, value.p);
    for (double& v : p) v = -v;
}

int cframe_inverse(lua_State* L) {
    auto* value = checked_cframe(L, 1);
    FrameVector p;
    FrameMatrix r;
    frame_inverse_parts(*value, p, r);
    return push_frame_value(L, p, r);
}

int push_frame_composition(lua_State* L, const FrameVector& p,
                           const FrameMatrix& r, const CFrameValue& other) {
    auto position = frame_rotate(r, other.p);
    for (int i = 0; i < 3; ++i) position[i] += p[i];
    return push_frame_value(L, position, frame_product(r, other.r));
}

int cframe_multiply(lua_State* L) {
    auto* a = checked_cframe(L, 1);
    if (lua_isvector(L, 2)) {
        auto p = frame_rotate(a->r, checked_frame_vector(L, 2));
        lua_pushvector(L, p[0]+a->p[0], p[1]+a->p[1], p[2]+a->p[2]);
        return 1;
    }
    return push_frame_composition(L, a->p, a->r, *checked_cframe(L, 2));
}

int cframe_translate(lua_State* L, double sign) {
    auto* a = checked_cframe(L, 1, false);
    auto offset = checked_frame_vector(L, 2);
    auto* value = new_cframe(L);
    *value = *a;
    for (int i = 0; i < 3; ++i) value->p[i] += sign*offset[i];
    // Position-only operations are possible even when a received rotation has
    // not been decoded. Preserve that metadata, including in serialized writes.
    if (!value->rotation_known)
        value->source["position"] = {encode_number(value->p[0]),
            encode_number(value->p[1]), encode_number(value->p[2])};
    luaL_getmetatable(L, kCFrameMeta);
    lua_setmetatable(L, -2);
    return 1;
}
int cframe_add(lua_State* L) { return cframe_translate(L, 1); }
int cframe_subtract(lua_State* L) { return cframe_translate(L, -1); }

int cframe_space(lua_State* L, bool inverse, bool vectors, bool translate) {
    auto* value = checked_cframe(L, 1);
    int count = lua_gettop(L)-1;
    // The methods accept tuples and return one result per supplied argument.
    // Validate the whole tuple before allocating the output userdata.
    for (int i = 2; i < count+2; ++i) {
        if (vectors) checked_frame_vector(L, i);
        else checked_cframe(L, i);
    }
    luaL_checkstack(L, count+2, "too many CFrame transform results");
    FrameVector p = value->p;
    FrameMatrix r = value->r;
    if (inverse) frame_inverse_parts(*value, p, r);
    for (int i = 2; i < count+2; ++i) {
        if (vectors) {
            auto result = frame_rotate(r, checked_frame_vector(L, i));
            if (translate)
                for (int j = 0; j < 3; ++j) result[j] += p[j];
            lua_pushvector(L, result[0], result[1], result[2]);
        } else {
            push_frame_composition(L, p, r, *checked_cframe(L, i));
        }
    }
    return count;
}
int cframe_world(lua_State* L) { return cframe_space(L, false, false, true); }
int cframe_object(lua_State* L) { return cframe_space(L, true, false, true); }
int cframe_point_world(lua_State* L) { return cframe_space(L, false, true, true); }
int cframe_point_object(lua_State* L) { return cframe_space(L, true, true, true); }
int cframe_vector_world(lua_State* L) { return cframe_space(L, false, true, false); }
int cframe_vector_object(lua_State* L) { return cframe_space(L, true, true, false); }

int cframe_euler(lua_State* L, bool yxz) {
    float x = static_cast<float>(finite_frame_angle(L, 1));
    float y = static_cast<float>(finite_frame_angle(L, 2));
    float z = static_cast<float>(finite_frame_angle(L, 3));
    float cx=static_cast<float>(std::cos(double(x))), sx=static_cast<float>(std::sin(double(x)));
    float cy=static_cast<float>(std::cos(double(y))), sy=static_cast<float>(std::sin(double(y)));
    float cz=static_cast<float>(std::cos(double(z))), sz=static_cast<float>(std::sin(double(z)));
    using FM = std::array<float, 9>;
    FM rx{1,0,0, 0,cx,-sx, 0,sx,cx};
    FM ry{cy,0,sy, 0,1,0, -sy,0,cy};
    FM rz{cz,-sz,0, sz,cz,0, 0,0,1};
    auto mul=[](const FM& a, const FM& b){
        FM r{};
        for(int i=0;i<3;++i)for(int j=0;j<3;++j){
            float acc=0;
            for(int k=0;k<3;++k)acc=static_cast<float>(acc+static_cast<float>(a[3*i+k]*b[3*k+j]));
            r[3*i+j]=acc;
        }
        return r;
    };
    FM rot = mul(mul(yxz ? ry : rx, yxz ? rx : ry), rz);
    FrameMatrix r{};
    for(int i=0;i<9;++i)r[i]=static_cast<double>(rot[i]);
    return push_frame_value(L, {}, r);
}
int cframe_euler_xyz(lua_State* L) { return cframe_euler(L, false); }
int cframe_euler_yxz(lua_State* L) { return cframe_euler(L, true); }

int cframe_axis_angle(lua_State* L) {
    auto axis = checked_frame_vector(L, 1);
    double angle = finite_frame_angle(L, 2);
    double length = std::hypot(axis[0], axis[1], axis[2]);
    if (!std::isfinite(length) || length == 0)
        luaL_error(L, "CFrame axis must be finite and nonzero");
    double x=axis[0]/length, y=axis[1]/length, z=axis[2]/length;
    double c=std::cos(angle), s=std::sin(angle), t=1-c;
    return push_frame_value(L, {}, {
        c+x*x*t, x*y*t-z*s, x*z*t+y*s,
        y*x*t+z*s, c+y*y*t, y*z*t-x*s,
        z*x*t-y*s, z*y*t+x*s, c+z*z*t});
}

void frame_method(lua_State* L, const char* name, lua_CFunction function) {
    lua_pushcfunction(L, function, name);
    lua_setfield(L, -2, name);
}

#include "cframe_orientation.inc"

void install_frame_methods(lua_State* L) {
    install_frame_orientation_methods(L);
    frame_method(L, "__mul", cframe_multiply);
    frame_method(L, "__add", cframe_add);
    frame_method(L, "__sub", cframe_subtract);
    frame_method(L, "Inverse", cframe_inverse);
    frame_method(L, "ToWorldSpace", cframe_world);
    frame_method(L, "ToObjectSpace", cframe_object);
    frame_method(L, "PointToWorldSpace", cframe_point_world);
    frame_method(L, "PointToObjectSpace", cframe_point_object);
    frame_method(L, "VectorToWorldSpace", cframe_vector_world);
    frame_method(L, "VectorToObjectSpace", cframe_vector_object);
    const char* aliases[][2]={
        {"inverse","Inverse"},{"lerp","Lerp"},
        {"toWorldSpace","ToWorldSpace"},{"toObjectSpace","ToObjectSpace"},
        {"pointToWorldSpace","PointToWorldSpace"},{"pointToObjectSpace","PointToObjectSpace"},
        {"vectorToWorldSpace","VectorToWorldSpace"},{"vectorToObjectSpace","VectorToObjectSpace"},
        {"toEulerAnglesXYZ","ToEulerAnglesXYZ"},{"toEulerAnglesYXZ","ToEulerAnglesYXZ"},
        {"toAxisAngle","ToAxisAngle"},
    };
    for(const auto& alias:aliases){lua_getfield(L,-1,alias[1]);lua_setfield(L,-2,alias[0]);}
}

void install_frame_constructors(lua_State* L) {
    install_frame_orientation_constructors(L);
    frame_method(L, "Angles", cframe_euler_xyz);
    frame_method(L, "fromEulerAnglesXYZ", cframe_euler_xyz);
    frame_method(L, "fromEulerAnglesYXZ", cframe_euler_yxz);
    frame_method(L, "fromOrientation", cframe_euler_yxz);
    frame_method(L, "fromAxisAngle", cframe_axis_angle);
}
