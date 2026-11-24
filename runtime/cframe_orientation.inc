// Ordinary orientation math for authored scripts. Included after the common
// CFrame helpers; all returned values use the existing snapshot userdata.
using FrameQuaternion = std::array<double, 4>; // x, y, z, w

FrameVector frame_cross(const FrameVector& a, const FrameVector& b) {
    return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]};
}
double frame_dot(const FrameVector& a, const FrameVector& b) {
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
}
FrameVector frame_unit(lua_State* L, FrameVector v) {
    double length = std::hypot(v[0], v[1], v[2]);
    if (!std::isfinite(length) || length == 0)
        luaL_error(L, "CFrame direction must be finite and nonzero");
    for (double& x : v) x /= length;
    return v;
}
FrameVector finite_frame_vector(lua_State* L, int index) {
    auto v = checked_frame_vector(L, index);
    for (double x : v)
        if (!std::isfinite(x)) luaL_error(L, "CFrame vector must be finite");
    return v;
}
FrameMatrix frame_columns(const FrameVector& x, const FrameVector& y, const FrameVector& z) {
    return {x[0],y[0],z[0], x[1],y[1],z[1], x[2],y[2],z[2]};
}
// A CFrame stores its rotation in single precision; constructors computed in double must round the result the way the engine
// does (lookAt/lookAlong verified bit for bit against the live client with this plain rounding).
FrameMatrix round_frame_matrix_to_float(FrameMatrix m) {
    for (double& v : m) v = static_cast<double>(static_cast<float>(v));
    return m;
}

FrameQuaternion frame_quaternion_unit(lua_State* L, FrameQuaternion q) {
    double scale = 0;
    for (double x : q) {
        if (!std::isfinite(x)) luaL_error(L, "CFrame quaternion must be finite");
        scale = std::max(scale, std::fabs(x));
    }
    if (scale == 0) luaL_error(L, "CFrame quaternion must be nonzero");
    double square = 0;
    for (double& x : q) { x /= scale; square += x*x; }
    double length = std::sqrt(square);
    for (double& x : q) x /= length;
    return q;
}
FrameMatrix frame_quaternion_matrix(const FrameQuaternion& q) {
    double x=q[0], y=q[1], z=q[2], w=q[3];
    return {1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w),
            2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w),
            2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)};
}
FrameQuaternion frame_matrix_quaternion(lua_State* L, const FrameMatrix& r) {
    for (double x : r)
        if (!std::isfinite(x)) luaL_error(L, "CFrame rotation must be finite");
    FrameQuaternion q{};
    // Select the largest quaternion component to avoid division by a tiny
    // scalar component near a half turn.
    double trace = r[0]+r[4]+r[8];
    if (trace > 0) {
        double s=2*std::sqrt(trace+1);
        q={(r[7]-r[5])/s, (r[2]-r[6])/s, (r[3]-r[1])/s, s/4};
    } else if (r[0] >= r[4] && r[0] >= r[8]) {
        double s=2*std::sqrt(std::max(0.0, 1+r[0]-r[4]-r[8]));
        q={s/4, (r[1]+r[3])/s, (r[2]+r[6])/s, (r[7]-r[5])/s};
    } else if (r[4] >= r[8]) {
        double s=2*std::sqrt(std::max(0.0, 1+r[4]-r[0]-r[8]));
        q={(r[1]+r[3])/s, s/4, (r[5]+r[7])/s, (r[2]-r[6])/s};
    } else {
        double s=2*std::sqrt(std::max(0.0, 1+r[8]-r[0]-r[4]));
        q={(r[2]+r[6])/s, (r[5]+r[7])/s, s/4, (r[3]-r[1])/s};
    }
    return frame_quaternion_unit(L, q);
}

int cframe_quaternion_new(lua_State* L) {
    FrameVector p;
    FrameQuaternion q;
    for (int i=0; i<3; ++i) {
        p[i]=luaL_checknumber(L, i+1);
        if (!std::isfinite(p[i])) luaL_error(L, "CFrame position must be finite");
    }
    for (int i=0; i<4; ++i) q[i]=luaL_checknumber(L, i+4);
    return push_frame_value(L, p, frame_quaternion_matrix(frame_quaternion_unit(L, q)));
}

using FrameF3 = std::array<float, 3>;
float f3_dot(const FrameF3& a, const FrameF3& b) { float s=a[0]*b[0]; s=s+a[1]*b[1]; s=s+a[2]*b[2]; return s; }
FrameF3 f3_cross(const FrameF3& a, const FrameF3& b) {
    return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]};
}
float f3_length(const FrameF3& a) { return static_cast<float>(std::sqrt(static_cast<double>(f3_dot(a, a)))); }
FrameF3 f3_unit_reciprocal(const FrameF3& a) {
    const float l=f3_length(a);
    const float r=1.0f/l;
    return {a[0]*r, a[1]*r, a[2]*r};
}

// CFrame.lookAt / lookAlong in single precision (fitted to four live-client results, all 36 components bit for bit):
//   forward = (target - position, in float) * (1/|.|);  right = unit(forward x up);  up' = right x forward;  back = -forward
// with |.| = sqrtf(left-to-right float dot) and 1/|.| a float reciprocal. No renormalization of up'.
int cframe_look(lua_State* L, bool target_point) {
    auto p=finite_frame_vector(L, 1);
    auto direction=finite_frame_vector(L, 2);
    FrameF3 d{static_cast<float>(direction[0]),static_cast<float>(direction[1]),static_cast<float>(direction[2])};
    if (target_point)
        for (int i=0; i<3; ++i) d[i]=d[i]-static_cast<float>(p[i]);
    const float d_length=f3_length(d);
    if (!std::isfinite(d_length) || d_length == 0)
        luaL_error(L, "CFrame direction must be finite and nonzero");
    const FrameF3 forward=f3_unit_reciprocal(d);
    FrameF3 up{0,1,0};
    if (!lua_isnoneornil(L, 3)) {
        auto u=frame_unit(L, finite_frame_vector(L, 3));
        up={static_cast<float>(u[0]),static_cast<float>(u[1]),static_cast<float>(u[2])};
    }
    FrameF3 right=f3_cross(forward, up);
    if (!(f3_length(right) >= 1e-6f)) {
        // The up direction cannot determine roll when parallel to the view.
        // Use X at the vertical pole, and Z if X is itself parallel.
        up=std::fabs(forward[0]) < .9f ? FrameF3{1,0,0} : FrameF3{0,0,1};
        right=f3_cross(forward, up);
    }
    right=f3_unit_reciprocal(right);
    const FrameF3 up_out=f3_cross(right, forward);
    FrameMatrix r{right[0],up_out[0],-forward[0], right[1],up_out[1],-forward[1], right[2],up_out[2],-forward[2]};
    return push_frame_value(L, p, r);
}
int cframe_look_at(lua_State* L) { return cframe_look(L, true); }
int cframe_look_along(lua_State* L) { return cframe_look(L, false); }

int cframe_lerp(lua_State* L) {
    auto* a=checked_cframe(L, 1);
    auto* b=checked_cframe(L, 2);
    double alpha=luaL_checknumber(L, 3);
    if (!std::isfinite(alpha)) luaL_error(L, "CFrame interpolation alpha must be finite");
    if (alpha == 0) return push_frame_value(L, a->p, a->r);
    if (alpha == 1) return push_frame_value(L, b->p, b->r);
    auto qa=frame_matrix_quaternion(L, a->r), qb=frame_matrix_quaternion(L, b->r);
    double dot=0;
    for (int i=0; i<4; ++i) dot+=qa[i]*qb[i];
    if (dot < 0) { for (double& v : qb) v=-v; dot=-dot; }
    dot=std::clamp(dot, 0.0, 1.0);
    double sine=std::sqrt(std::max(0.0, 1-dot*dot));
    double wa=1-alpha, wb=alpha;
    if (sine > 1e-8) {
        double angle=std::atan2(sine, dot);
        wa=std::sin((1-alpha)*angle)/sine;
        wb=std::sin(alpha*angle)/sine;
    }
    FrameQuaternion q;
    for (int i=0; i<4; ++i) q[i]=wa*qa[i]+wb*qb[i];
    FrameVector p;
    // Position interpolates in single precision with a float alpha (verified against the live client).
    const float alpha_f=static_cast<float>(alpha);
    for (int i=0; i<3; ++i) {
        const float from=static_cast<float>(a->p[i]), to=static_cast<float>(b->p[i]);
        const float delta=to-from;
        const float step=delta*alpha_f;
        p[i]=static_cast<double>(from+step);
    }
    return push_frame_value(L, p, round_frame_matrix_to_float(frame_quaternion_matrix(frame_quaternion_unit(L, q))));
}

int cframe_to_axis_angle(lua_State* L) {
    auto q=frame_matrix_quaternion(L, checked_cframe(L, 1)->r);
    if (q[3] < 0) for (double& v : q) v=-v;
    double length=std::hypot(q[0], q[1], q[2]);
    if (length == 0) lua_pushvector(L, 1,0,0);
    else lua_pushvector(L, q[0]/length, q[1]/length, q[2]/length);
    lua_pushnumber(L, 2*std::atan2(length, q[3]));
    return 2;
}

double frame_rotation_angle(lua_State* L,const FrameMatrix& left,const FrameMatrix& right) {
    auto a=frame_matrix_quaternion(L,left);
    auto b=frame_matrix_quaternion(L,right);
    // The vector part of conjugate(a)*b remains accurate near zero angle.
    FrameVector relative{
        a[3]*b[0]-a[0]*b[3]-a[1]*b[2]+a[2]*b[1],
        a[3]*b[1]+a[0]*b[2]-a[1]*b[3]-a[2]*b[0],
        a[3]*b[2]-a[0]*b[1]+a[1]*b[0]-a[2]*b[3]};
    double scalar=0;
    for (int i=0; i<4; ++i) scalar+=a[i]*b[i];
    return 2*std::atan2(std::hypot(relative[0],relative[1],relative[2]), std::fabs(scalar));
}
int cframe_angle_between(lua_State* L) {
    lua_pushnumber(L,frame_rotation_angle(L,checked_cframe(L,1)->r,checked_cframe(L,2)->r));
    return 1;
}

FrameF3 f3_unit(const FrameF3& a) { const float l=f3_length(a); return {a[0]/l, a[1]/l, a[2]/l}; }

// CFrame.new(position, lookAt) is built differently from CFrame.lookAt, in single precision with reciprocal-length normalization
// (verified against the live client: seven random cases plus a protected script's call, all 63 components bit for bit):
//   z = (position - lookAt) * (1/|.|);  y' = unit(up - z*(up.z));  x = unit(y' x z);  y = z x x
// Looking straight along up degenerates y'; that case uses the look-at path.
int cframe_position_look_at(lua_State* L) {
    const auto p=finite_frame_vector(L, 1);
    const auto target=finite_frame_vector(L, 2);
    const FrameF3 back_raw{static_cast<float>(p[0])-static_cast<float>(target[0]),
                           static_cast<float>(p[1])-static_cast<float>(target[1]),
                           static_cast<float>(p[2])-static_cast<float>(target[2])};
    const float length=f3_length(back_raw);
    if (!std::isfinite(length) || length == 0)
        luaL_error(L, "CFrame direction must be finite and nonzero");
    const FrameF3 z=f3_unit_reciprocal(back_raw);
    const FrameF3 up{0, 1, 0};
    const float along=f3_dot(up, z);
    const FrameF3 gs{up[0]-z[0]*along, up[1]-z[1]*along, up[2]-z[2]*along};
    const float gs_length=f3_length(gs);
    if (!std::isfinite(gs_length) || gs_length < 1e-6f) return cframe_look(L, true);
    const FrameF3 y_seed=f3_unit_reciprocal(gs);
    // The engine builds x from z x y' and scales by a negated reciprocal, so an exactly-zero component comes out as -0
    // (live client, protected script call): same bits as unit(y' x z) everywhere else.
    const FrameF3 x_raw=f3_cross(z, y_seed);
    const float x_scale=-(1.0f/f3_length(x_raw));
    const FrameF3 x{x_raw[0]*x_scale, x_raw[1]*x_scale, x_raw[2]*x_scale};
    const FrameF3 y=f3_cross(z, x);
    FrameMatrix r{x[0],y[0],z[0], x[1],y[1],z[1], x[2],y[2],z[2]};
    return push_frame_value(L, p, r);
}
int cframe_rotation_between(lua_State* L) {
    // Validate like before (finite, nonzero), then work in single precision as the engine does: float unit vectors, a float
    // half-angle quaternion that is renormalized in float, and the standard quaternion matrix in float. This reproduces the live
    // client's result for perpendicular unit vectors bit for bit (its quaternion components come out one ulp above 1/sqrt(2));
    // for general inputs it agrees to within a few ulps.
    frame_unit(L, finite_frame_vector(L, 1));
    frame_unit(L, finite_frame_vector(L, 2));
    auto v1=finite_frame_vector(L, 1), v2=finite_frame_vector(L, 2);
    FrameF3 from=f3_unit({static_cast<float>(v1[0]),static_cast<float>(v1[1]),static_cast<float>(v1[2])});
    FrameF3 to=f3_unit({static_cast<float>(v2[0]),static_cast<float>(v2[1]),static_cast<float>(v2[2])});
    FrameF3 axis=f3_cross(from, to);
    const float sine=f3_length(axis);
    const float cosine=std::clamp(f3_dot(from, to), -1.0f, 1.0f);
    if (sine < 1e-12f && cosine > 0)
        return push_frame_value(L, {}, {1,0,0,0,1,0,0,0,1});
    if (sine < 1e-12f) {
        int least=0;
        for (int i=1; i<3; ++i) if (std::fabs(from[i]) < std::fabs(from[least])) least=i;
        FrameF3 basis{}; basis[least]=1;
        axis=f3_cross(from, basis);
    }
    axis=f3_unit(axis);
    const float angle=static_cast<float>(std::atan2(static_cast<double>(sine), static_cast<double>(cosine)));
    const float half=angle/2;
    const float s=static_cast<float>(std::sin(static_cast<double>(half))), w0=static_cast<float>(std::cos(static_cast<double>(half)));
    float x=axis[0]*s, y=axis[1]*s, z=axis[2]*s, w=w0;
    float n2=(x*x+y*y)+(z*z+w*w);
    const float n=static_cast<float>(std::sqrt(static_cast<double>(n2)));
    x=x/n; y=y/n; z=z/n; w=w/n;
    float m[9];
    m[0]=1.0f-2.0f*(y*y+z*z); m[1]=2.0f*(x*y-z*w);      m[2]=2.0f*(x*z+y*w);
    m[3]=2.0f*(x*y+z*w);      m[4]=1.0f-2.0f*(x*x+z*z); m[5]=2.0f*(y*z-x*w);
    m[6]=2.0f*(x*z-y*w);      m[7]=2.0f*(y*z+x*w);      m[8]=1.0f-2.0f*(x*x+y*y);
    FrameMatrix r{};
    for(int i=0;i<9;++i)r[i]=static_cast<double>(m[i]);
    return push_frame_value(L, {}, r);
}

FrameVector frame_euler_angles(const FrameMatrix& r,bool yxz) {
    double x, y, z;
    if (yxz) {
        x=std::asin(std::clamp(-r[5], -1.0, 1.0));
        if (std::fabs(std::cos(x)) > 1e-7) { y=std::atan2(r[2],r[8]); z=std::atan2(r[3],r[4]); }
        else { y=std::atan2(-r[6],r[0]); z=0; }
    } else {
        y=std::asin(std::clamp(r[2], -1.0, 1.0));
        if (std::fabs(std::cos(y)) > 1e-7) { x=std::atan2(-r[5],r[8]); z=std::atan2(-r[1],r[0]); }
        else { x=std::atan2(r[7],r[4]); z=0; }
    }
    return {x,y,z};
}
int cframe_to_euler(lua_State* L, bool yxz) {
    const auto& r=checked_cframe(L,1)->r;
    for(double v:r)if(!std::isfinite(v))luaL_error(L,"CFrame rotation must be finite");
    auto angles=frame_euler_angles(r,yxz);
    for(double value:angles)lua_pushnumber(L,value);
    return 3;
}
int cframe_to_euler_xyz(lua_State* L) { return cframe_to_euler(L, false); }
int cframe_to_euler_yxz(lua_State* L) { return cframe_to_euler(L, true); }

int cframe_orthonormalize(lua_State* L) {
    auto* value=checked_cframe(L, 1);
    auto x=frame_unit(L, {value->r[0],value->r[3],value->r[6]});
    FrameVector y{value->r[1],value->r[4],value->r[7]};
    auto z=frame_unit(L, frame_cross(x,y));
    y=frame_cross(z,x);
    return push_frame_value(L, value->p, frame_columns(x,y,z));
}

int geometry_rotation_order(lua_State* L,int index) {
    return lua_isnoneornil(L,index)?0:checked_geometry_value(L,index,kGeometryRotationOrder);
}
int cframe_from_euler_general(lua_State* L) {
    float x=static_cast<float>(finite_frame_angle(L,1)),y=static_cast<float>(finite_frame_angle(L,2)),z=static_cast<float>(finite_frame_angle(L,3));
    int order=geometry_rotation_order(L,4);
    // Same single-precision pipeline as CFrame.Angles (the live client returns identical values for fromEulerAngles(x,y,z,XYZ)).
    return push_frame_value(L,{},euler_float_matrix(x,y,z,kGeometryEnums[kGeometryRotationOrder].names[order]));
}
int cframe_to_euler_general(lua_State* L) {
    const auto& r=checked_cframe(L,1)->r;
    int order=geometry_rotation_order(L,2);
    for(double v:r)if(!std::isfinite(v))luaL_error(L,"CFrame rotation must be finite");
    const char* names=kGeometryEnums[kGeometryRotationOrder].names[order];
    int axes[3]={names[0]-'X',names[1]-'X',names[2]-'X'};
    // Conjugating by an axis permutation reduces every order to XYZ. An odd
    // permutation reverses handedness, so its recovered angles change sign.
    int inversions=(axes[0]>axes[1])+(axes[0]>axes[2])+(axes[1]>axes[2]);
    double sign=(inversions%2)?-1:1;
    FrameMatrix m;
    for(int row=0;row<3;++row)for(int col=0;col<3;++col)m[row*3+col]=r[axes[row]*3+axes[col]];
    FrameVector local;
    local[1]=std::asin(std::clamp(m[2],-1.0,1.0));
    if(std::fabs(std::cos(local[1]))>1e-7) {
        local[0]=std::atan2(-m[5],m[8]);local[2]=std::atan2(-m[1],m[0]);
    } else {local[0]=std::atan2(m[7],m[4]);local[2]=0;}
    FrameVector angles;
    for(int i=0;i<3;++i)angles[axes[i]]=sign*local[i];
    for(double angle:angles)lua_pushnumber(L,angle);
    return 3;
}

int cframe_fuzzy_eq(lua_State* L) {
    const auto* a=checked_cframe(L,1);const auto* b=checked_cframe(L,2);
    double epsilon=luaL_optnumber(L,3,1e-5);
    if(!std::isfinite(epsilon)||std::fabs(epsilon)>.1)
        luaL_error(L,"The eps value provided to FuzzyEq should be a small positive value <= 0.1");
    bool equal=true;
    for(size_t i=0;i<3;++i)equal=equal&&runtime_fuzzy_component(a->p[i],b->p[i],epsilon);
    // Orientation tolerance is the total relative angle, not a comparison of
    // matrix elements (which would depend on the world-space basis). The
    // relative angle is reconstructed from float32 matrix components, so a
    // small roundoff slack is required: Studio's own reference case 12 has an
    // angle of 0.010000037 for epsilon 0.01 and must compare equal. The slack
    // is far below the smallest false-case gap in that reference (0.012).
    equal=equal&&(a->r==b->r||frame_rotation_angle(L,a->r,b->r)<=std::fabs(epsilon)*(1+1e-4));
    lua_pushboolean(L,equal);return 1;
}

void install_frame_orientation_methods(lua_State* L) {
    frame_method(L,"FuzzyEq",cframe_fuzzy_eq);
    frame_method(L,"ToEulerAngles",cframe_to_euler_general);
    frame_method(L,"Lerp",cframe_lerp);
    frame_method(L,"ToAxisAngle",cframe_to_axis_angle);
    frame_method(L,"AngleBetween",cframe_angle_between);
    frame_method(L,"ToEulerAnglesXYZ",cframe_to_euler_xyz);
    frame_method(L,"ToEulerAnglesYXZ",cframe_to_euler_yxz);
    frame_method(L,"ToOrientation",cframe_to_euler_yxz);
    frame_method(L,"Orthonormalize",cframe_orthonormalize);
    frame_method(L,"components",cframe_components);
}
void install_frame_orientation_constructors(lua_State* L) {
    frame_method(L,"fromEulerAngles",cframe_from_euler_general);
    frame_method(L,"lookAt",cframe_look_at);
    frame_method(L,"lookAlong",cframe_look_along);
    frame_method(L,"fromRotationBetweenVectors",cframe_rotation_between);
}
