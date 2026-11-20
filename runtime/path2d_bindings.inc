// Path2DControlPoint values and the Path2D curve API (included into world_bindings.cpp).
//
// Behavior is checked against Roblox Studio: error texts, argument conversion, the control-point list versus the
// internal spline, parent requirements. Luraph-protected scripts hash Path2D results into their decryption keys, so
// the curve math follows the engine's float32 evaluation order exactly: power-basis coefficients, adaptive-bisection
// length, RK4 arc length. Every intermediate is rounded to float32 where the engine rounds it, through p2d_f32().

struct Path2DControlPointValue {
    double px; int32_t pxo; double py; int32_t pyo;
    double ltx; int32_t ltxo; double lty; int32_t ltyo;
    double rtx; int32_t rtxo; double rty; int32_t rtyo;
};
constexpr const char* kPath2DControlPointMeta="HeadlessRuntime.Path2DControlPoint";
constexpr size_t kPath2DMaxControlPoints=100;

// Engine-bound methods raise plain messages without a source position.
[[noreturn]] void p2d_raise(lua_State* L,const std::string& message) {
    lua_pushlstring(L,message.data(),message.size());
    lua_error(L);
}
bool path2d_control_points_equal(const Path2DControlPointValue& a,const Path2DControlPointValue& b) {
    return a.px==b.px&&a.pxo==b.pxo&&a.py==b.py&&a.pyo==b.pyo&&a.ltx==b.ltx&&a.ltxo==b.ltxo
        &&a.lty==b.lty&&a.ltyo==b.ltyo&&a.rtx==b.rtx&&a.rtxo==b.rtxo&&a.rty==b.rty&&a.rtyo==b.rtyo;
}
void push_path2d_control_point(lua_State* L,const Path2DControlPointValue& value) {
    auto* out=static_cast<Path2DControlPointValue*>(lua_newuserdatatagged(L,sizeof(Path2DControlPointValue),0));
    *out=value;luaL_getmetatable(L,kPath2DControlPointMeta);lua_setmetatable(L,-2);
}
Path2DControlPointValue* path2d_control_point_userdata(lua_State* L,int index) {
    if(!has_meta(L,index,kPath2DControlPointMeta))luaL_typeerror(L,index,"Path2DControlPoint");
    return static_cast<Path2DControlPointValue*>(lua_touserdata(L,index));
}

// The constructor takes no arguments, a position, or position and both tangents; any other count is rejected.
int path2d_control_point_new(lua_State* L) {
    const int count=lua_gettop(L);
    if(count!=0&&count!=1&&count!=3)p2d_raise(L,"Trying to create a Path2DControlPoint with wrong number of arguments");
    Path2DControlPointValue value{};
    auto read_udim2_argument=[&](int index,double& sx,int32_t& ox,double& sy,int32_t& oy) {
        if(!read_udim2_raw(L,index,sx,ox,sy,oy))luaL_typeerror(L,index,"UDim2");
    };
    if(count>=1)read_udim2_argument(1,value.px,value.pxo,value.py,value.pyo);
    if(count==3) {
        read_udim2_argument(2,value.ltx,value.ltxo,value.lty,value.ltyo);
        read_udim2_argument(3,value.rtx,value.rtxo,value.rty,value.rtyo);
    }
    push_path2d_control_point(L,value);return 1;
}
int path2d_control_point_index(lua_State* L) {
    const auto* value=path2d_control_point_userdata(L,1);
    std::string key=luaL_checkstring(L,2);
    if(key=="Position"){push_udim2_raw(L,value->px,value->pxo,value->py,value->pyo);return 1;}
    if(key=="LeftTangent"){push_udim2_raw(L,value->ltx,value->ltxo,value->lty,value->ltyo);return 1;}
    if(key=="RightTangent"){push_udim2_raw(L,value->rtx,value->rtxo,value->rty,value->rtyo);return 1;}
    p2d_raise(L,"'"+key+"' is not a valid member of Path2DControlPoint");
}
// The point object itself is mutable; the Path2D keeps its own copy of every point it is given.
int path2d_control_point_newindex(lua_State* L) {
    auto* value=path2d_control_point_userdata(L,1);
    std::string key=luaL_checkstring(L,2);
    if(key=="Position"||key=="LeftTangent"||key=="RightTangent") {
        double sx=0,sy=0;int32_t ox=0,oy=0;
        if(!read_udim2_raw(L,3,sx,ox,sy,oy))luaL_typeerror(L,3,"UDim2");
        if(key=="Position"){value->px=sx;value->pxo=ox;value->py=sy;value->pyo=oy;}
        else if(key=="LeftTangent"){value->ltx=sx;value->ltxo=ox;value->lty=sy;value->ltyo=oy;}
        else{value->rtx=sx;value->rtxo=ox;value->rty=sy;value->rtyo=oy;}
        return 0;
    }
    p2d_raise(L,key+" is not a valid member of Path2DControlPoint");
}
int path2d_control_point_eq(lua_State* L) {
    const bool both=has_meta(L,1,kPath2DControlPointMeta)&&has_meta(L,2,kPath2DControlPointMeta);
    lua_pushboolean(L,both&&path2d_control_points_equal(*static_cast<Path2DControlPointValue*>(lua_touserdata(L,1)),
                                                        *static_cast<Path2DControlPointValue*>(lua_touserdata(L,2))));
    return 1;
}
int path2d_control_point_tostring(lua_State* L) {
    const auto* value=path2d_control_point_userdata(L,1);
    auto udim2_text=[&](double sx,int32_t ox,double sy,int32_t oy) {
        push_udim2_raw(L,sx,ox,sy,oy);
        luaL_callmeta(L,-1,"__tostring");
        size_t length=0;const char* text=lua_tolstring(L,-1,&length);
        std::string result(text?text:"",text?length:0);lua_pop(L,2);return result;
    };
    std::string text="Path2DControlPoint { Position = "+udim2_text(value->px,value->pxo,value->py,value->pyo)
        +", LeftTangent = "+udim2_text(value->ltx,value->ltxo,value->lty,value->ltyo)
        +", RightTangent = "+udim2_text(value->rtx,value->rtxo,value->rty,value->rtyo)+" }";
    lua_pushlstring(L,text.data(),text.size());return 1;
}

// Path2D keeps two structures. points is the control-point list (SetControlPoints replaces it, Insert/Update/Remove
// edit it). spline is the size of the engine's internal spline: only a successful Insert grows it and Remove shrinks
// it, and Update/Remove need an existing spline slot. List edits are applied before the spline operation can fail.
struct Path2DState {
    std::vector<Path2DControlPointValue> points;
    int spline=0;
};
using Path2DStates=std::unordered_map<std::string,Path2DState>;
std::unordered_map<const World*,Path2DStates>& path2d_store() {
    thread_local std::unordered_map<const World*,Path2DStates> store;
    return store;
}
Path2DState& path2d_state_for(const World& w,const std::string& id) {return path2d_store()[&w][id];}
const std::vector<Path2DControlPointValue>& path2d_points_const(const World& w,const std::string& id) {
    static const std::vector<Path2DControlPointValue> empty;
    auto world=path2d_store().find(&w);
    if(world==path2d_store().end())return empty;
    auto node=world->second.find(id);
    return node==world->second.end()?empty:node->second.points;
}
Handle* checked_path2d(lua_State* L) {
    Handle* h=checked_handle(L,1);
    if(h->node->destroyed){luaL_error(L,"Path2D receiver is destroyed");return nullptr;}
    if(h->node->class_name!="Path2D"){luaL_error(L,"Path2D receiver required");return nullptr;}
    return h;
}
bool path2d_is_closed(World& w,Node& n) {
    const auto* closed=property_value(w,n,"Closed");
    return closed&&closed->is_boolean()&&closed->get<bool>();
}
// A closed path adds the closing segment only from three points up.
size_t path2d_segment_count(const std::vector<Path2DControlPointValue>& points,bool closed) {
    if(points.size()<2)return 0;
    return closed&&points.size()>=3?points.size():points.size()-1;
}
// Curve queries and Insert/Update need the Path2D to sit directly in a GUI container.
bool path2d_parent_valid(World& w,Node& n) {
    Node* parent=find_node(w,parent_id(w,n));
    return parent&&!parent->destroyed&&class_is_a(w,parent->class_name,"GuiBase2d");
}

// The pixel size control points resolve against: the nearest GuiObject/ScreenGui ancestor. A mounted tree
// uses the real layout; an unmounted one starts from the engine's 800x600 viewport and applies each Size.
void path2d_canvas_size(World& w,Node& n,double& out_w,double& out_h) {
    out_w=0;out_h=0;
    std::string current=parent_id(w,n);
    for(int hop=0;hop<128&&!current.empty();++hop) {
        Node* parent=find_node(w,current);
        if(!parent||parent->destroyed)break;
        if(parent->class_name=="ScreenGui"||parent->id==w.overlay_root||gui_object(w,*parent)) {
            try {
                GuiLayoutPass pass{w};
                GuiBox box=pass.box(*parent);
                if(box.attached){out_w=box.width;out_h=box.height;return;}
            } catch(const std::exception&) {}
            double width=800,height=600;
            std::vector<Node*> chain;
            Node* scan=parent;
            for(int depth=0;depth<32&&scan;++depth) {
                if(scan->class_name=="ScreenGui"||scan->id==w.overlay_root)break;
                if(!gui_object(w,*scan))break;
                chain.push_back(scan);
                scan=find_node(w,parent_id(w,*scan));
            }
            for(auto it=chain.rbegin();it!=chain.rend();++it) {
                const auto* size=property_value(w,**it,"Size");
                if(size&&size->is_object()&&size->contains("$udim2")&&(*size)["$udim2"].is_array()&&(*size)["$udim2"].size()==2) {
                    const auto& x=(*size)["$udim2"][0].at("$udim");
                    const auto& y=(*size)["$udim2"][1].at("$udim");
                    width=std::max(0.0,x.at(0).get<double>()*width+x.at(1).get<double>());
                    height=std::max(0.0,y.at(0).get<double>()*height+y.at(1).get<double>());
                }
            }
            out_w=width;out_h=height;return;
        }
        current=parent_id(w,*parent);
    }
}

float p2d_f32(double value) {return static_cast<float>(value);}
struct Path2DBezier {
    int n=0;
    float x0=0,y0=0,c1x=0,c1y=0,c2x=0,c2y=0,c3x=0,c3y=0;
    float length=0;bool length_known=false;
};
float p2d_resolve(double scale,double offset,double dimension) {return p2d_f32(p2d_f32(scale*dimension)+offset);}
// Power-basis coefficients with the engine's association. s holds n points (x,y pairs): 2 = line,
// 3 = quadratic, 4 = cubic; a zero tangent leaves its handle out.
Path2DBezier p2d_coefficients(const float* s,int n) {
    Path2DBezier c;c.n=n;c.x0=s[0];c.y0=s[1];
    const float x0=s[0],y0=s[1];
    if(n==2) {
        c.c1x=p2d_f32(s[2]-x0);c.c1y=p2d_f32(s[3]-y0);
    } else if(n==3) {
        const float x1=s[2],y1=s[3],x2=s[4],y2=s[5];
        c.c1x=p2d_f32(p2d_f32(x1-x0)*2);c.c1y=p2d_f32(p2d_f32(y1-y0)*2);
        c.c2x=p2d_f32(p2d_f32(x0-p2d_f32(x1*2))+x2);
        c.c2y=p2d_f32(p2d_f32(y0-p2d_f32(y1*2))+y2);
    } else {
        const float x1=s[2],y1=s[3],x2=s[4],y2=s[5],x3=s[6],y3=s[7];
        c.c1x=p2d_f32(p2d_f32(x1-x0)*3);c.c1y=p2d_f32(p2d_f32(y1-y0)*3);
        c.c2x=p2d_f32(p2d_f32(p2d_f32(x0-p2d_f32(x1*2))+x2)*3);
        c.c2y=p2d_f32(p2d_f32(p2d_f32(y0-p2d_f32(y1*2))+y2)*3);
        c.c3x=p2d_f32(p2d_f32(p2d_f32(x3-x0)+p2d_f32(x1*3))-p2d_f32(x2*3));
        c.c3y=p2d_f32(p2d_f32(p2d_f32(y3-y0)+p2d_f32(y1*3))-p2d_f32(y2*3));
    }
    return c;
}
Path2DBezier path2d_segment(const std::vector<Path2DControlPointValue>& points,size_t index,double width,double height) {
    const auto& a=points[index];
    const auto& b=points[(index+1)%points.size()];
    const float apx=p2d_resolve(a.px,a.pxo,width),apy=p2d_resolve(a.py,a.pyo,height);
    const float arx=p2d_resolve(a.rtx,a.rtxo,width),ary=p2d_resolve(a.rty,a.rtyo,height);
    const float bpx=p2d_resolve(b.px,b.pxo,width),bpy=p2d_resolve(b.py,b.pyo,height);
    const float blx=p2d_resolve(b.ltx,b.ltxo,width),bly=p2d_resolve(b.lty,b.ltyo,height);
    float s[8];int count=0;
    s[count++]=apx;s[count++]=apy;
    if(arx!=0.0f||ary!=0.0f){s[count++]=p2d_f32(apx+arx);s[count++]=p2d_f32(apy+ary);}
    if(blx!=0.0f||bly!=0.0f){s[count++]=p2d_f32(bpx+blx);s[count++]=p2d_f32(bpy+bly);}
    s[count++]=bpx;s[count++]=bpy;
    return p2d_coefficients(s,count/2);
}
std::vector<Path2DBezier> p2d_segments(const std::vector<Path2DControlPointValue>& points,size_t count,double width,double height) {
    std::vector<Path2DBezier> segments;segments.reserve(count);
    for(size_t i=0;i<count;++i)segments.push_back(path2d_segment(points,i,width,height));
    return segments;
}
void p2d_position(const Path2DBezier& c,double u,double& x,double& y) {
    const float t=p2d_f32(u);
    if(c.n==2) {
        x=p2d_f32(c.x0+p2d_f32(c.c1x*t));y=p2d_f32(c.y0+p2d_f32(c.c1y*t));
    } else if(c.n==3) {
        x=p2d_f32(c.x0+p2d_f32(p2d_f32(c.c1x+p2d_f32(c.c2x*t))*t));
        y=p2d_f32(c.y0+p2d_f32(p2d_f32(c.c1y+p2d_f32(c.c2y*t))*t));
    } else {
        const float ix=p2d_f32(c.c2x+p2d_f32(c.c3x*t)),iy=p2d_f32(c.c2y+p2d_f32(c.c3y*t));
        x=p2d_f32(c.x0+p2d_f32(p2d_f32(c.c1x+p2d_f32(ix*t))*t));
        y=p2d_f32(c.y0+p2d_f32(p2d_f32(c.c1y+p2d_f32(iy*t))*t));
    }
}
// B(u) - P0: the engine's length routine leaves the start point out, which changes the rounding.
void p2d_offset(const Path2DBezier& c,float u,float& x,float& y) {
    if(c.n==2) {
        x=p2d_f32(c.c1x*u);y=p2d_f32(c.c1y*u);
    } else if(c.n==3) {
        x=p2d_f32(p2d_f32(c.c1x+p2d_f32(c.c2x*u))*u);y=p2d_f32(p2d_f32(c.c1y+p2d_f32(c.c2y*u))*u);
    } else {
        const float ix=p2d_f32(c.c2x+p2d_f32(c.c3x*u)),iy=p2d_f32(c.c2y+p2d_f32(c.c3y*u));
        x=p2d_f32(p2d_f32(c.c1x+p2d_f32(ix*u))*u);y=p2d_f32(p2d_f32(c.c1y+p2d_f32(iy*u))*u);
    }
}
// The derivative with respect to the segment parameter, in pixels (not normalized).
void p2d_tangent(const Path2DBezier& c,double u,double& tx,double& ty) {
    const float t=p2d_f32(u);
    if(c.n==2) {
        tx=c.c1x;ty=c.c1y;
    } else if(c.n==3) {
        const float k=p2d_f32(t*2);
        tx=p2d_f32(c.c1x+p2d_f32(c.c2x*k));ty=p2d_f32(c.c1y+p2d_f32(c.c2y*k));
    } else {
        const float k=p2d_f32(3*t);
        tx=p2d_f32(c.c1x+p2d_f32(t*p2d_f32(p2d_f32(c.c2x*2)+p2d_f32(c.c3x*k))));
        ty=p2d_f32(c.c1y+p2d_f32(t*p2d_f32(p2d_f32(c.c2y*2)+p2d_f32(c.c3y*k))));
    }
}
float p2d_distance(float ax,float ay,float bx,float by) {
    const float dx=p2d_f32(bx-ax),dy=p2d_f32(by-ay);
    return p2d_f32(std::sqrt(p2d_f32(p2d_f32(dx*dx)+p2d_f32(dy*dy))));
}
// Adaptive bisection: chord a against the two half chords b; stop once b - a < 1e-5, else sum the halves.
float p2d_segment_length_recursive(const Path2DBezier& c,float t0,float t1,float x0,float y0,float x1,float y1,int depth) {
    const float tm=p2d_f32(p2d_f32(t0+t1)*0.5f);
    float xm=0,ym=0;p2d_offset(c,tm,xm,ym);
    const float a=p2d_distance(x0,y0,x1,y1);
    const float b=p2d_f32(p2d_distance(x0,y0,xm,ym)+p2d_distance(xm,ym,x1,y1));
    if(depth>=30||p2d_f32(b-a)<p2d_f32(1e-5))return b;
    return p2d_f32(p2d_segment_length_recursive(c,t0,tm,x0,y0,xm,ym,depth+1)+p2d_segment_length_recursive(c,tm,t1,xm,ym,x1,y1,depth+1));
}
float p2d_segment_length(const Path2DBezier& c) {
    float x0=0,y0=0,x1=0,y1=0;
    p2d_offset(c,0.0f,x0,y0);p2d_offset(c,1.0f,x1,y1);
    return p2d_segment_length_recursive(c,0.0f,1.0f,x0,y0,x1,y1,0);
}
float p2d_total_length(std::vector<Path2DBezier>& segments) {
    float total=0;
    for(auto& c:segments) {
        if(!c.length_known){c.length=p2d_segment_length(c);c.length_known=true;}
        total=p2d_f32(total+c.length);
    }
    return total;
}
// Arc length s (pixels from the segment start) -> parameter u: 32 classic RK4 steps of du/ds = 1/|B'(u)|.
float p2d_arc_parameter(const Path2DBezier& c,float s) {
    const float sixth=p2d_f32(1.0/6.0);
    const float d2x=p2d_f32(c.c2x*2),d2y=p2d_f32(c.c2y*2);
    float d3x=0,d3y=0;
    if(c.n==4){d3x=p2d_f32(c.c3x*3);d3y=p2d_f32(c.c3y*3);}
    auto inverse_speed=[&](float u)->double {
        float dx,dy;
        if(c.n==3) {
            dx=p2d_f32(c.c1x+p2d_f32(d2x*u));dy=p2d_f32(c.c1y+p2d_f32(d2y*u));
        } else {
            dx=p2d_f32(c.c1x+p2d_f32(u*p2d_f32(d2x+p2d_f32(u*d3x))));
            dy=p2d_f32(c.c1y+p2d_f32(u*p2d_f32(d2y+p2d_f32(u*d3y))));
        }
        return std::sqrt(p2d_f32(p2d_f32(dx*dx)+p2d_f32(dy*dy)));
    };
    const float h=p2d_f32(s/32);
    float u=0;
    for(int step=0;step<32;++step) {
        const float k1=p2d_f32(h/p2d_f32(inverse_speed(u)));
        const float k2=p2d_f32(h/p2d_f32(inverse_speed(p2d_f32(u+p2d_f32(k1*0.5f)))));
        const float k3=p2d_f32(h/p2d_f32(inverse_speed(p2d_f32(u+p2d_f32(k2*0.5f)))));
        const float k4=p2d_f32(h/p2d_f32(inverse_speed(p2d_f32(u+k3))));
        u=p2d_f32(u+p2d_f32(p2d_f32(p2d_f32(k1+p2d_f32(2*p2d_f32(k2+k3)))+k4)*sixth));
    }
    return u;
}
// t in [0,1] -> segment and local parameter (GetPositionOnCurve / GetTangentOnCurve).
void p2d_locate(const std::vector<Path2DBezier>& segments,double t,size_t& segment,double& u) {
    float clamped=p2d_f32(t);if(clamped<0)clamped=0;else if(clamped>1)clamped=1;
    const size_t count=segments.size();
    const float x=p2d_f32(clamped*static_cast<double>(count));
    const size_t index=std::min(static_cast<size_t>(std::floor(x)),count-1);
    segment=index;u=p2d_f32(x-static_cast<double>(index));
}
// Arc-length fraction -> segment and local parameter: the engine walks the segments, subtracting each length.
void p2d_locate_arc(std::vector<Path2DBezier>& segments,double t,size_t& segment,double& u) {
    float clamped=p2d_f32(t);if(clamped<0)clamped=0;else if(clamped>1)clamped=1;
    const float total=p2d_total_length(segments);
    float s=p2d_f32(clamped*total);
    for(size_t i=0;i<segments.size();++i) {
        const auto& c=segments[i];
        if(s<=c.length){segment=i;u=(c.n==2)?p2d_f32(s/c.length):p2d_arc_parameter(c,s);return;}
        s=p2d_f32(s-c.length);
    }
    segment=0;u=0;
}

// Argument conversion the way engine-bound methods report it: "Argument N missing or nil" and "Unable to cast X to Y".
const char* p2d_cast_type(lua_State* L,int index) {
    switch(lua_type(L,index)) {
        case LUA_TNUMBER:return "double";
        case LUA_TBOOLEAN:return "bool";
        case LUA_TSTRING:return "string";
        default:return luaL_typename(L,index);
    }
}
void p2d_require_argument(lua_State* L,int index,int number) {
    if(lua_isnoneornil(L,index))p2d_raise(L,"Argument "+std::to_string(number)+" missing or nil");
}
double p2d_number_argument(lua_State* L,int index,int number,const char* target) {
    p2d_require_argument(L,index,number);
    if(!lua_isnumber(L,index))p2d_raise(L,std::string("Unable to cast ")+p2d_cast_type(L,index)+" to "+target);
    return lua_tonumber(L,index);
}
// A fractional index rounds half away from zero.
int p2d_index_argument(lua_State* L,int index,int number) {
    const double value=p2d_number_argument(L,index,number,"int");
    if(std::isnan(value))return 0;
    return static_cast<int>(std::clamp(std::round(value),-2147483648.0,2147483647.0));
}
Path2DControlPointValue p2d_point_argument(lua_State* L,int index,int number) {
    p2d_require_argument(L,index,number);
    if(!has_meta(L,index,kPath2DControlPointMeta))
        p2d_raise(L,std::string("Unable to cast ")+p2d_cast_type(L,index)+" to Path2DControlPoint");
    return *static_cast<const Path2DControlPointValue*>(lua_touserdata(L,index));
}
std::string p2d_bounds_message(const char* method,int index) {
    return std::string("Path2D:")+method+"() at index "+std::to_string(index)+" access out of bounds";
}
void p2d_require_parent(lua_State* L,World& w,Node& n) {
    if(!path2d_parent_valid(w,n))p2d_raise(L,"Attempting to use Path2D with invalid parent");
}

// A successful curve query rebuilds the internal spline from the control-point list.
void path2d_sync_spline(World& w,Node& n) {
    auto& state=path2d_state_for(w,n.id);
    state.spline=static_cast<int>(state.points.size());
}

// Shared setup for the curve queries: converts t, rejects an empty path, requires a GUI parent, builds the segments.
struct Path2DCurve {
    std::vector<Path2DBezier> segments;
    double width=0,height=0;
};
Path2DCurve path2d_curve(lua_State* L,Handle* h,const char* method,double* t) {
    if(t) {
        double value=p2d_number_argument(L,2,1,"float");
        if(std::isnan(value))value=0;
        *t=std::clamp(value,0.0,1.0);
    }
    World& w=*h->world;Node& n=*h->node;
    const auto& points=path2d_points_const(w,n.id);
    const size_t count=path2d_segment_count(points,path2d_is_closed(w,n));
    if(count==0)p2d_raise(L,std::string("Path2D:")+method+"() attempting to query with zero segments");
    p2d_require_parent(L,w,n);
    path2d_sync_spline(w,n);
    Path2DCurve curve;
    path2d_canvas_size(w,n,curve.width,curve.height);
    curve.segments=p2d_segments(points,count,curve.width,curve.height);
    return curve;
}
int push_path2d_position(lua_State* L,const Path2DCurve& curve,size_t segment,double u) {
    double x=0,y=0;
    p2d_position(curve.segments[segment],u,x,y);
    if(curve.width>0&&curve.height>0)push_udim2_raw(L,x/curve.width,0,y/curve.height,0);
    else push_udim2_raw(L,0,static_cast<int32_t>(std::trunc(x)),0,static_cast<int32_t>(std::trunc(y)));
    return 1;
}

int path2d_get_control_point(lua_State* L) {
    Handle* h=checked_path2d(L);
    const int index=p2d_index_argument(L,2,1);
    const auto& points=path2d_points_const(*h->world,h->node->id);
    if(index<1||static_cast<size_t>(index)>points.size())p2d_raise(L,p2d_bounds_message("GetControlPoint",index));
    push_path2d_control_point(L,points[static_cast<size_t>(index)-1]);return 1;
}
int path2d_get_control_points(lua_State* L) {
    Handle* h=checked_path2d(L);
    const auto& points=path2d_points_const(*h->world,h->node->id);
    lua_createtable(L,static_cast<int>(points.size()),0);
    for(size_t i=0;i<points.size();++i){push_path2d_control_point(L,points[i]);lua_rawseti(L,-2,static_cast<int>(i+1));}
    return 1;
}
int path2d_set_control_points(lua_State* L) {
    Handle* h=checked_path2d(L);
    p2d_require_argument(L,2,1);
    if(lua_type(L,2)!=LUA_TTABLE)p2d_raise(L,std::string("Unable to cast ")+p2d_cast_type(L,2)+" to Array");
    std::vector<Path2DControlPointValue> next;
    for(int i=1;;++i) {
        lua_rawgeti(L,2,i);
        if(lua_isnil(L,-1)){lua_pop(L,1);break;}
        if(static_cast<size_t>(i)>kPath2DMaxControlPoints){lua_pop(L,1);p2d_raise(L,"Path2D:SetControlPoints() only supports 100 control points.");}
        if(!has_meta(L,-1,kPath2DControlPointMeta)){lua_pop(L,1);p2d_raise(L,"Variant cast failed");}
        next.push_back(*static_cast<Path2DControlPointValue*>(lua_touserdata(L,-1)));
        lua_pop(L,1);
    }
    path2d_state_for(*h->world,h->node->id).points=std::move(next);
    emit(*h->world,*h->node,"ControlPointChanged",Json::array());
    return 0;
}
int path2d_insert_control_point(lua_State* L) {
    Handle* h=checked_path2d(L);
    const int index=p2d_index_argument(L,2,1);
    const auto point=p2d_point_argument(L,3,2);
    World& w=*h->world;Node& n=*h->node;
    auto& state=path2d_state_for(w,n.id);
    if(state.points.size()>=kPath2DMaxControlPoints)p2d_raise(L,"Path2D:InsertControlPoint() only supports 100 control points.");
    if(index<1||static_cast<size_t>(index)>state.points.size()+1)p2d_raise(L,p2d_bounds_message("InsertControlPoint",index));
    p2d_require_parent(L,w,n);
    state.points.insert(state.points.begin()+(index-1),point);
    emit(w,n,"ControlPointChanged",Json::array({index}));
    if(index-1>state.spline)p2d_raise(L,"Spline inserting control point at index "+std::to_string(index-1)+" access out of bounds");
    ++state.spline;
    return 0;
}
int path2d_update_control_point(lua_State* L) {
    Handle* h=checked_path2d(L);
    const int index=p2d_index_argument(L,2,1);
    const auto point=p2d_point_argument(L,3,2);
    World& w=*h->world;Node& n=*h->node;
    auto& state=path2d_state_for(w,n.id);
    if(index<1||static_cast<size_t>(index)>state.points.size())p2d_raise(L,p2d_bounds_message("UpdateControlPoint",index));
    p2d_require_parent(L,w,n);
    state.points[static_cast<size_t>(index-1)]=point;
    emit(w,n,"ControlPointChanged",Json::array({index}));
    if(index-1>=state.spline)p2d_raise(L,"Spline updating control point at index "+std::to_string(index-1)+" access out of bounds");
    return 0;
}
int path2d_remove_control_point(lua_State* L) {
    Handle* h=checked_path2d(L);
    const int index=p2d_index_argument(L,2,1);
    World& w=*h->world;Node& n=*h->node;
    auto& state=path2d_state_for(w,n.id);
    if(index<1||static_cast<size_t>(index)>state.points.size())p2d_raise(L,p2d_bounds_message("RemoveControlPoint",index));
    state.points.erase(state.points.begin()+(index-1));
    emit(w,n,"ControlPointChanged",Json::array({index}));
    if(index-1>=state.spline)p2d_raise(L,"Spline removing control point at index "+std::to_string(index-1)+" access out of bounds");
    --state.spline;
    return 0;
}
// Scripts running without the RobloxScript capability (game scripts) cannot use the segment count.
int path2d_get_segment_count(lua_State* L) {
    checked_path2d(L);
    p2d_raise(L,"The current thread cannot call 'GetSegmentCount' (lacking capability RobloxScript)");
}
int path2d_get_max_control_points(lua_State* L) {
    checked_path2d(L);
    lua_pushinteger(L,static_cast<lua_Integer>(kPath2DMaxControlPoints));return 1;
}
int path2d_get_length(lua_State* L) {
    Handle* h=checked_path2d(L);
    World& w=*h->world;Node& n=*h->node;
    const auto& points=path2d_points_const(w,n.id);
    const size_t count=path2d_segment_count(points,path2d_is_closed(w,n));
    double length=0;
    if(count>0) {
        p2d_require_parent(L,w,n);
        path2d_sync_spline(w,n);
        double width=0,height=0;
        path2d_canvas_size(w,n,width,height);
        auto segments=p2d_segments(points,count,width,height);
        length=p2d_total_length(segments);
    }
    lua_pushnumber(L,length);return 1;
}
int path2d_get_position_on_curve(lua_State* L) {
    Handle* h=checked_path2d(L);
    double t=0;auto curve=path2d_curve(L,h,"GetPositionOnCurve",&t);
    size_t segment=0;double u=0;p2d_locate(curve.segments,t,segment,u);
    return push_path2d_position(L,curve,segment,u);
}
int path2d_get_position_on_curve_arc_length(lua_State* L) {
    Handle* h=checked_path2d(L);
    double t=0;auto curve=path2d_curve(L,h,"GetPositionOnCurveArcLength",&t);
    size_t segment=0;double u=0;p2d_locate_arc(curve.segments,t,segment,u);
    return push_path2d_position(L,curve,segment,u);
}
int path2d_get_tangent_on_curve(lua_State* L) {
    Handle* h=checked_path2d(L);
    double t=0;auto curve=path2d_curve(L,h,"GetTangentOnCurve",&t);
    size_t segment=0;double u=0;p2d_locate(curve.segments,t,segment,u);
    double tx=0,ty=0;p2d_tangent(curve.segments[segment],u,tx,ty);
    return push_vector2(L,tx,ty);
}
int path2d_get_tangent_on_curve_arc_length(lua_State* L) {
    Handle* h=checked_path2d(L);
    double t=0;auto curve=path2d_curve(L,h,"GetTangentOnCurveArcLength",&t);
    size_t segment=0;double u=0;p2d_locate_arc(curve.segments,t,segment,u);
    double tx=0,ty=0;p2d_tangent(curve.segments[segment],u,tx,ty);
    return push_vector2(L,tx,ty);
}
// The control points and the curve's axis extrema, padded by half the stroke thickness plus half a pixel. A path
// without a segment reports the widest representable rectangle.
int path2d_get_bounding_rect(lua_State* L) {
    Handle* h=checked_path2d(L);
    World& w=*h->world;Node& n=*h->node;
    const auto& points=path2d_points_const(w,n.id);
    const size_t count=path2d_segment_count(points,path2d_is_closed(w,n));
    double min_x,min_y,max_x,max_y;
    if(count==0) {
        const double widest=static_cast<double>(std::numeric_limits<float>::max());
        min_x=min_y=-widest;max_x=max_y=widest;
    } else {
        p2d_require_parent(L,w,n);
        path2d_sync_spline(w,n);
        double width=0,height=0;
        path2d_canvas_size(w,n,width,height);
        // The engine places a control point in single precision: float(scale * canvas) first, then the float offset
        // (live client: a point's y of 0.0509576946*507+12 comes out one float below the all-double result).
        auto place=[](double scale,double canvas,float offset) {
            return static_cast<double>(static_cast<float>(static_cast<double>(static_cast<float>(scale*canvas))+static_cast<double>(offset)));
        };
        min_x=max_x=place(points[0].px,width,points[0].pxo);
        min_y=max_y=place(points[0].py,height,points[0].pyo);
        auto expand=[&](double x,double y) {
            if(x<min_x)min_x=x;
            if(x>max_x)max_x=x;
            if(y<min_y)min_y=y;
            if(y>max_y)max_y=y;
        };
        for(const auto& point:points)expand(place(point.px,width,point.pxo),place(point.py,height,point.pyo));
        const auto segments=p2d_segments(points,count,width,height);
        for(const auto& segment:segments) {
            auto check_axis=[&](float c1,float c2,float c3) {
                double roots[2];int root_count=0;
                if(segment.n==4) {
                    const double a=3.0*c3,b=2.0*c2,c=c1;
                    if(std::abs(a)<1e-12) {
                        if(std::abs(b)>1e-12)roots[root_count++]=-c/b;
                    } else {
                        const double discriminant=b*b-4.0*a*c;
                        if(discriminant>=0.0) {
                            const double root=std::sqrt(discriminant);
                            roots[root_count++]=(-b+root)/(2.0*a);
                            roots[root_count++]=(-b-root)/(2.0*a);
                        }
                    }
                } else if(segment.n==3) {
                    const double b=2.0*c2;
                    if(std::abs(b)>1e-12)roots[root_count++]=-static_cast<double>(c1)/b;
                }
                for(int i=0;i<root_count;++i) {
                    if(roots[i]>0.0&&roots[i]<1.0){double x=0,y=0;p2d_position(segment,roots[i],x,y);expand(x,y);}
                }
            };
            check_axis(segment.c1x,segment.c2x,segment.c3x);
            check_axis(segment.c1y,segment.c2y,segment.c3y);
        }
        double thickness=1.0;
        if(const auto* value=property_value(w,n,"Thickness");value&&value->is_number())thickness=value->get<double>();
        const double padding=thickness>0.0?0.5*thickness+0.5:0.0;
        const auto padded=[padding](double value,double sign) {
            return static_cast<double>(static_cast<float>(static_cast<double>(static_cast<float>(value))+sign*static_cast<double>(static_cast<float>(padding))));
        };
        min_x=padded(min_x,-1);min_y=padded(min_y,-1);max_x=padded(max_x,1);max_y=padded(max_y,1);
    }
    auto f32=[](double v){return static_cast<double>(static_cast<float>(v));};
    push_authored_value(L,Json{{"$rect",Json::array({Json{{"$vector2",Json::array({f32(min_x),f32(min_y)})}},Json{{"$vector2",Json::array({f32(max_x),f32(max_y)})}}})}});
    return 1;
}

// Member lookup for Path2D instances; returns false for members this class does not add.
bool path2d_index(lua_State* L,const std::string& key) {
    struct Method {const char* name;lua_CFunction function;};
    static const Method methods[]={
        {"GetControlPoint",path2d_get_control_point},{"GetControlPoints",path2d_get_control_points},
        {"SetControlPoints",path2d_set_control_points},{"InsertControlPoint",path2d_insert_control_point},
        {"UpdateControlPoint",path2d_update_control_point},{"RemoveControlPoint",path2d_remove_control_point},
        {"GetPositionOnCurve",path2d_get_position_on_curve},{"GetPositionOnCurveArcLength",path2d_get_position_on_curve_arc_length},
        {"GetTangentOnCurve",path2d_get_tangent_on_curve},{"GetTangentOnCurveArcLength",path2d_get_tangent_on_curve_arc_length},
        {"GetLength",path2d_get_length},{"GetSegmentCount",path2d_get_segment_count},
        {"GetMaxControlPoints",path2d_get_max_control_points},{"GetBoundingRect",path2d_get_bounding_rect},
    };
    for(const auto& method:methods) {
        if(key==method.name){lua_pushcfunction(L,method.function,method.name);return true;}
    }
    if(key=="SelectedControlPoint"||key=="SelectedControlPointData")
        p2d_raise(L,"The current thread cannot read '"+key+"' (lacking capability RobloxScript)");
    return false;
}
void install_path2d_bindings(lua_State* L) {
    luaL_newmetatable(L,kPath2DControlPointMeta);
    lua_pushcfunction(L,path2d_control_point_index,"__index");lua_setfield(L,-2,"__index");
    // No debug name: the engine reports this error as "invalid argument #3 (...)" without naming the function.
    lua_pushcfunction(L,path2d_control_point_newindex,nullptr);lua_setfield(L,-2,"__newindex");
    lua_pushcfunction(L,path2d_control_point_eq,"__eq");lua_setfield(L,-2,"__eq");
    lua_pushcfunction(L,path2d_control_point_tostring,"__tostring");lua_setfield(L,-2,"__tostring");
    lua_pushliteral(L,"Path2DControlPoint");lua_setfield(L,-2,"__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_pop(L,1);
    lua_createtable(L,0,1);
    lua_pushcfunction(L,path2d_control_point_new,"new");lua_setfield(L,-2,"new");
    lua_setreadonly(L,-1,true);lua_setglobal(L,"Path2DControlPoint");
}
