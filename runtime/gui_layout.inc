// Local display surface and the ordinary ScreenGui/GuiObject box model.
// This is layout state, not a renderer. Unsupported layout dependencies fail
// explicitly. Insets are total margins from the full surface (L,T,R,B).
Json validated_display(const Json& supplied) {
    if (!supplied.is_object() || !supplied.contains("size") || supplied.size()>4)
        throw std::runtime_error("display requires size and optional safe-area margins");
    Json out{{"size",Json::array({0,0})},{"device_insets",Json::array({0,0,0,0})},
             {"core_insets",Json::array({0,0,0,0})}};
    for(auto it=supplied.begin();it!=supplied.end();++it) {
        const auto& key=it.key();size_t count=key=="size"?2:4;
        if(key!="size"&&key!="device_insets"&&key!="core_insets"&&key!="topbar_insets")
            throw std::runtime_error("unknown display field");
        if(!it->is_array()||it->size()!=count)throw std::runtime_error("invalid display dimensions");
        for(const auto& v:*it)if(!v.is_number()||!std::isfinite(v.get<double>())||v.get<double>()<0||v.get<double>()>32768)
            throw std::runtime_error("display dimensions must be finite numbers in 0..32768");
        out[key]=*it;
    }
    if(!supplied.contains("core_insets"))out["core_insets"]=out["device_insets"];
    for(const char* key:{"device_insets","core_insets","topbar_insets"})if(out.contains(key)) {
        const auto& m=out[key];
        if(m[0].get<double>()+m[2].get<double>()>out["size"][0].get<double>()||
           m[1].get<double>()+m[3].get<double>()>out["size"][1].get<double>())
            throw std::runtime_error("display insets exceed surface size");
        if(std::strcmp(key,"device_insets")!=0)for(int i=0;i<4;i++)
            if(m[i].get<double>()<out["device_insets"][i].get<double>())
                throw std::runtime_error("UI safe area must be inside device safe area");
    }
    return out;
}
bool gui_object(World& w,const Node& n) {return class_is_a(w,n.class_name,"GuiObject");}
bool gui_image(const Node& n) {return n.class_name=="ImageLabel"||n.class_name=="ImageButton";}
bool padding_property(const std::string& key) {
    return key=="PaddingLeft"||key=="PaddingRight"||key=="PaddingTop"||key=="PaddingBottom";
}
int gui_enum_kind(World& w,const Node& n,const std::string& key) {
    if(gui_image(n)) {
        if(key=="ScaleType")return kImageScaleType;
        if(key=="ResampleMode")return kImageResamplerMode;
    }
    if(n.class_name=="UIGradient") {
        if(key=="TileMode")return kGradientTileMode;
        if(key=="Type")return kGradientType;
    }
    if(n.class_name=="UIStroke") {
        if(key=="ApplyStrokeMode")return kApplyStrokeMode;
        if(key=="StrokeSizingMode")return kStrokeSizingMode;
        if(key=="BorderStrokePosition")return kBorderStrokePosition;
        if(key=="LineJoinMode")return kLineJoinMode;
    }
    if(n.class_name=="UIFlexItem") {
        if(key=="FlexMode")return kGuiFlexMode;
        if(key=="ItemLineAlignment")return kGuiItemLineAlignment;
    }
    if(n.class_name=="ScrollingFrame") {
        if(key=="AutomaticCanvasSize")return kGuiAutomaticSize;
        if(key=="ScrollingDirection")return kGuiScrollingDirection;
        if(key=="HorizontalScrollBarInset"||key=="VerticalScrollBarInset")return kGuiScrollBarInset;
        if(key=="VerticalScrollBarPosition")return kGuiVerticalScrollBarPosition;
    }
    if(n.class_name=="TextLabel"||n.class_name=="TextButton"||n.class_name=="TextBox") {
        if(key=="TextXAlignment")return kTextXAlignment;
        if(key=="TextYAlignment")return kTextYAlignment;
        if(key=="TextDirection")return kTextDirection;
        if(key=="TextTruncate")return kTextTruncate;
    }
    if(n.class_name=="UIListLayout"||n.class_name=="UIGridLayout") {
        if(key=="FillDirection")return kGuiFillDirection;
        if(key=="HorizontalAlignment")return kGuiHorizontalAlignment;
        if(key=="VerticalAlignment")return kGuiVerticalAlignment;
        if(key=="SortOrder")return kGuiSortOrder;
        if(n.class_name=="UIGridLayout"&&key=="StartCorner")return kGuiStartCorner;
        if(n.class_name=="UIListLayout") {
            if(key=="HorizontalFlex"||key=="VerticalFlex")return kGuiFlexAlignment;
            if(key=="ItemLineAlignment")return kGuiItemLineAlignment;
        }
    }
    if(n.class_name=="UIAspectRatioConstraint") {
        if(key=="AspectType")return kGuiAspectType;
        if(key=="DominantAxis")return kGuiDominantAxis;
    }
    if(!gui_object(w,n))return -1;
    if(key=="SizeConstraint")return kGuiSizeConstraint;
    if(key=="AutomaticSize")return kGuiAutomaticSize;
    return -1;
}
std::string gui_property_type(World& w,const Node& n,const std::string& key) {
    if(n.class_name=="UIGradient") {
        if(key=="Offset")return "Vector2";
        if(key=="Rotation"||key=="Scale")return "number";
        if(gui_enum_kind(w,n,key)>=0)return "EnumItem";
    }
    if(n.class_name=="StarterGui"&&key=="ClipsDescendantsSupportsRotation")return "boolean";
    if(gui_object(w,n)&&key=="ClipsDescendants")return "boolean";
    if(n.class_name=="UIGridLayout") {
        if(key=="CellSize"||key=="CellPadding")return "UDim2";
        if(key=="FillDirectionMaxCells")return "number";
        if(gui_enum_kind(w,n,key)>=0)return "EnumItem";
    }
    if(n.class_name=="UIFlexItem") {
        if(key=="GrowRatio"||key=="ShrinkRatio")return "number";
        if(gui_enum_kind(w,n,key)>=0)return "EnumItem";
    }
    if(n.class_name=="ScrollingFrame") {
        if(key=="CanvasSize")return "UDim2";
        if(key=="CanvasPosition")return "Vector2";
        if(key=="ScrollBarImageColor3")return "Color3";
        if(key=="ScrollBarThickness")return "number";
    }
    if(n.class_name=="UIListLayout") {
        if(key=="Padding")return "UDim";
        if(key=="Wraps")return "boolean";
        if(gui_enum_kind(w,n,key)>=0)return "EnumItem";
    }
    if(n.class_name=="UICorner"&&key=="CornerRadius")return "UDim";
    if(n.class_name=="UIStroke") {
        if(key=="Color")return "Color3";
        if(key=="BorderOffset")return "UDim";
        if(gui_enum_kind(w,n,key)>=0)return "EnumItem";
    }
    if(n.class_name=="UISizeConstraint"&&(key=="MinSize"||key=="MaxSize"))return "Vector2";
    if(n.class_name=="UIAspectRatioConstraint") {
        if(key=="AspectRatio")return "number";
        if(gui_enum_kind(w,n,key)>=0)return "EnumItem";
    }
    if(n.class_name=="UIPadding"&&padding_property(key))return "UDim";
    if(n.class_name=="UIScale"&&key=="Scale")return "number";
    if(gui_object(w,n)) {
        if(key=="BackgroundColor3"||key=="BorderColor3")return "Color3";
        if((n.class_name=="TextLabel"||n.class_name=="TextButton"||n.class_name=="TextBox")&&
                (key=="TextColor3"||key=="TextStrokeColor3"))return "Color3";
        if(gui_image(n)) {
            if(key=="ImageColor3")return "Color3";
            if(key=="ImageRectOffset"||key=="ImageRectSize")return "Vector2";
            if(key=="TileSize")return "UDim2";
        }
        if(key=="Size"||key=="Position")return "UDim2";
        if(key=="AnchorPoint")return "Vector2";
        if(key=="Rotation")return "number";
        if(gui_enum_kind(w,n,key)>=0)return "EnumItem";
    }
    return "";
}
const Json* gui_default_property(World& w,const Node& n,const std::string& key) {
    static const Json clipping_off=false,clipping_on=true;
    if(n.class_name=="TextBox"&&key=="PlaceholderColor3")return &property_descriptor(n,key)->at("value");
    if(key=="TextTruncate"&&gui_enum_kind(w,n,key)==kTextTruncate)return &property_descriptor(n,key)->at("value");
    if(key=="TextStrokeColor3"&&text_layout_node(n))return &property_descriptor(n,key)->at("value");
    if(n.class_name=="UIStroke"&&(gui_enum_kind(w,n,key)>=0||key=="BorderOffset"))return &property_descriptor(n,key)->at("value");
    if(n.class_name=="UIGradient"&&(key=="Color"||key=="Transparency"||key=="Offset"||gui_enum_kind(w,n,key)>=0))return &property_descriptor(n,key)->at("value");
    if(gui_image(n)&&(key=="ImageColor3"||key=="ImageRectOffset"||key=="ImageRectSize"||key=="TileSize"||key=="ScaleType"||key=="ResampleMode"))
        return &property_descriptor(n,key)->at("value");
    if(n.class_name=="StarterGui"&&key=="ClipsDescendantsSupportsRotation")return &clipping_off;
    if(gui_object(w,n)&&key=="ClipsDescendants")return n.class_name=="ScrollingFrame"?&clipping_on:&clipping_off;
    static const Json zero=0,one=1,origin=Json{{"$vector2",{0,0}}},
        padding=Json{{"$udim",{0,0}}},position=Json{{"$udim2",Json::array({padding,padding})}};
    static const Json unbounded=Json{{"$vector2",Json::array({Json{{"$number","inf"}},Json{{"$number","inf"}}})}};
    static const Json corner=Json{{"$udim",{0,8}}},black=Json{{"$color3",{0,0,0}}};
    if(n.class_name=="UIGridLayout") {
        static const Json cell={{"$udim2",Json::array({Json{{"$udim",{0,100}}},Json{{"$udim",{0,100}}}})}};
        static const Json spacing={{"$udim2",Json::array({Json{{"$udim",{0,5}}},Json{{"$udim",{0,5}}}})}},order=2;
        if(key=="CellSize")return &cell;
        if(key=="CellPadding")return &spacing;
        if(key=="FillDirection"||key=="StartCorner"||key=="FillDirectionMaxCells")return &zero;
        if(key=="HorizontalAlignment"||key=="VerticalAlignment")return &one;
        if(key=="SortOrder")return &order;
    }
    if(n.class_name=="UIFlexItem"&&(key=="FlexMode"||key=="ItemLineAlignment"||key=="GrowRatio"||key=="ShrinkRatio"))return &zero;
    if(n.class_name=="ScrollingFrame") {
        static const Json xy=4,enabled=true,canvas={{"$udim2",Json::array({padding,Json{{"$udim",{2,0}}}})}};
        if(key=="CanvasPosition")return &origin;
        if(key=="CanvasSize")return &canvas;
        if(key=="ScrollingDirection")return &xy;
        if(key=="ScrollingEnabled")return &enabled;
        if(key=="AutomaticCanvasSize"||key=="HorizontalScrollBarInset"||key=="VerticalScrollBarInset"||key=="VerticalScrollBarPosition")return &zero;
    }
    if(n.class_name=="UIListLayout") {
        static const Json no=false;
        if(key=="Padding")return &padding;
        if(key=="Wraps")return &no;
        if(key=="FillDirection"||key=="HorizontalAlignment"||key=="VerticalAlignment")return &one;
        if(key=="SortOrder"||key=="HorizontalFlex"||key=="VerticalFlex"||key=="ItemLineAlignment")return &zero;
    }
    if(n.class_name=="UICorner"&&key=="CornerRadius")return &corner;
    if(n.class_name=="UIStroke"&&key=="Color")return &black;
    if(n.class_name=="UISizeConstraint") {
        if(key=="MinSize")return &origin;
        if(key=="MaxSize")return &unbounded;
    }
    if(n.class_name=="UIPadding"&&padding_property(key))return &padding;
    if(n.class_name=="UIScale"&&key=="Scale")return &one;
    if(n.class_name=="UIAspectRatioConstraint") {
        if(key=="AspectRatio")return &one;
        if(key=="AspectType"||key=="DominantAxis")return &zero;
    }
    if(gui_object(w,n)) {
        if(key=="Rotation"||key=="SizeConstraint"||key=="AutomaticSize")return &zero;
        if(key=="AnchorPoint")return &origin;
        if(key=="Position")return &position;
    }
    return nullptr; // Class-specific default sizes are not inferred.
}
int gui_enum_value(World& w,const Node& n,const std::string& key) {
    int kind=gui_enum_kind(w,n,key);
    if(kind<0)throw std::runtime_error("unknown GUI enum property");
    const Json* stored=property_value(w,n,key);
    if(!stored)throw std::runtime_error("GUI enum property unavailable");
    const Json* raw=stored;
    if(stored->is_object()&&stored->contains("$enum")) {
        const auto& e=stored->at("$enum");
        if(!e.is_object()||e.value("type","")!=kGeometryEnums[kind].name||!e.contains("value"))
            throw std::runtime_error("GUI enum type mismatch");
        raw=&e.at("value");
    }
    if(!raw->is_number_integer())throw std::runtime_error("invalid GUI enum value");
    int value=-1;
    for(int i=0;i<kGeometryEnums[kind].count;i++)if(*raw==geometry_numeric(kind,i)){value=i;break;}
    if(value<0)throw std::runtime_error("invalid GUI enum value");
    if(stored->is_object()&&stored->at("$enum").contains("name")&&
       stored->at("$enum").at("name")!=kGeometryEnums[kind].names[value])
        throw std::runtime_error("GUI enum name/value mismatch");
    return value;
}
std::array<double,2> gui_size_bound(const Json& value,bool maximum) {
    if(!value.is_object()||!value.contains("$vector2"))throw std::runtime_error("size constraint requires Vector2");
    const auto& a=value.at("$vector2");
    if(!a.is_array()||a.size()!=2)throw std::runtime_error("invalid size constraint vector");
    std::array<double,2> result;
    for(int i=0;i<2;i++) {
        if(maximum&&a[i]==Json{{"$number","inf"}})result[i]=std::numeric_limits<double>::infinity();
        else {
            if(!a[i].is_number())throw std::runtime_error("size constraint components must be nonnegative; only MaxSize permits infinity");
            result[i]=a[i].get<double>();
            if(!std::isfinite(result[i])||result[i]<0)throw std::runtime_error("size constraint components must be finite and nonnegative");
        }
    }
    return result;
}
void validate_gui_bounds(const std::array<double,2>& minimum,const std::array<double,2>& maximum) {
    if(minimum[0]>maximum[0]||minimum[1]>maximum[1])throw std::runtime_error("MinSize must not exceed MaxSize");
}
bool validate_gui_assignment(lua_State* L,World& w,const Node& n,const std::string& key) {
    auto type=gui_property_type(w,n,key);if(type.empty())return false;
    if(type=="EnumItem") {
        if(!has_meta(L,3,kGeometryItemMeta)||
           static_cast<GeometryEnumItem*>(lua_touserdata(L,3))->kind!=gui_enum_kind(w,n,key))
            throw std::runtime_error("incorrect enum type for GUI property");
    } else if(type=="boolean") {
        if(lua_type(L,3)!=LUA_TBOOLEAN)throw std::runtime_error("GUI property requires a boolean");
    } else if(type=="number") {
        if(lua_type(L,3)!=LUA_TNUMBER||!std::isfinite(lua_tonumber(L,3)))throw std::runtime_error("GUI property requires a finite number");
        if(n.class_name=="UIScale"&&lua_tonumber(L,3)<0)throw std::runtime_error("negative UIScale is unsupported");
        if(n.class_name=="UIAspectRatioConstraint"&&key=="AspectRatio"&&lua_tonumber(L,3)<=0)
            throw std::runtime_error("AspectRatio must be greater than zero");
        if(n.class_name=="ScrollingFrame"&&key=="ScrollBarThickness"&&lua_tonumber(L,3)<0)
            throw std::runtime_error("ScrollBarThickness must be nonnegative");
        if(n.class_name=="UIFlexItem"&&lua_tonumber(L,3)<0)
            throw std::runtime_error("flex ratios must be nonnegative");
        if(n.class_name=="UIGridLayout"&&key=="FillDirectionMaxCells") {
            double value=lua_tonumber(L,3);
            if(value<0||value>2147483647||std::floor(value)!=value)
                throw std::runtime_error("FillDirectionMaxCells requires a nonnegative integer");
        }
    } else if(!is_authored_value(L,3)||type!=luaL_typename(L,3))
        throw std::runtime_error("Unable to assign property "+key+". "+type+" expected, got "+(lua_type(L,3)==LUA_TNONE?std::string("nil"):std::string(luaL_typename(L,3))));
    if((n.class_name=="UIStroke"&&key=="BorderOffset")||(n.class_name=="UIGradient"&&key=="Offset")) {
        Json supplied;capture_authored_value(L,3,supplied);
        for(const auto& value:supplied.at(key=="Offset"?"$vector2":"$udim"))
            if(!value.is_number()||!std::isfinite(value.get<double>()))throw std::runtime_error(key+" must be finite");
    }
    if(n.class_name=="ScrollingFrame"&&(key=="CanvasPosition"||key=="CanvasSize")) {
        Json supplied;capture_authored_value(L,3,supplied);
        const auto& components=supplied.at(key=="CanvasPosition"?"$vector2":"$udim2");
        for(const auto& component:components) {
            if(key=="CanvasPosition") {
                if(!component.is_number()||!std::isfinite(component.get<double>()))throw std::runtime_error("CanvasPosition must be finite");
            } else for(const auto& v:component.at("$udim"))
                if(!v.is_number()||!std::isfinite(v.get<double>()))throw std::runtime_error("CanvasSize must be finite");
        }
    }
    if(n.class_name=="UISizeConstraint") {
        Json supplied;capture_authored_value(L,3,supplied);
        const Json* min=key=="MinSize"?&supplied:property_value(w,n,"MinSize");
        const Json* max=key=="MaxSize"?&supplied:property_value(w,n,"MaxSize");
        if(!min||!max)throw std::runtime_error("size constraint bounds unavailable");
        validate_gui_bounds(gui_size_bound(*min,false),gui_size_bound(*max,true));
    }
    return true;
}
bool display_property(World& w,const Node& n,const std::string& key) {
    if(n.class_name=="ScrollingFrame"&&(key=="AbsoluteCanvasSize"||key=="AbsoluteWindowSize"||key=="CanvasPosition"))return true;
    if((n.class_name=="UIListLayout"||n.class_name=="UIGridLayout")&&key=="AbsoluteContentSize")return true;
    if(n.class_name=="UIGridLayout"&&(key=="AbsoluteCellSize"||key=="AbsoluteCellCount"))return true;
    return ((n.class_name=="ScreenGui"||gui_object(w,n))&&
         (key=="AbsoluteSize"||key=="AbsolutePosition"||key=="AbsoluteRotation"));
}
bool display_readonly_property(World& w,const Node& n,const std::string& key) {
    return display_property(w,n,key)&&!(n.class_name=="ScrollingFrame"&&key=="CanvasPosition");
}
Json display_vector(double x,double y) {return Json{{"$vector2",Json::array({x,y})}};}
// Keep the camera projection backend and GUI surface on the same host input.
Json display_from_viewport(const Json& vp) {
    const auto& d=vp.at("device_safe_insets");const auto& g=vp.at("gui_inset");
    return Json{{"size",vp.at("size")},{"device_insets",d},
        {"core_insets",Json::array({d[0].get<double>()+g[0].get<double>(),d[1].get<double>()+g[1].get<double>(),d[2],d[3]})}};
}
void update_display(World& w,const Json& supplied) {
    auto profile=validated_display(supplied);
    const auto& s=profile["size"];const auto& d=profile["device_insets"];const auto& c=profile["core_insets"];
    // A zero-area surface is detached. Preserve the last camera viewport, as
    // inactive cameras do, while GUI layout reports the empty surface.
    if(s[0].get<double>()>c[0].get<double>()+c[2].get<double>()&&s[1].get<double>()>c[1].get<double>()+c[3].get<double>())
        update_viewport(w,Json{{"size",s},{"device_safe_insets",d},
            {"gui_inset",Json::array({c[0].get<double>()-d[0].get<double>(),c[1].get<double>()-d[1].get<double>()})}});
    w.display=std::move(profile);
}
double layout_number(World& w,const Node& n,const char* key,double fallback) {
    const auto* v=property_value(w,n,key);if(!v)return fallback;
    if(!v->is_number()||!std::isfinite(v->get<double>()))throw std::runtime_error(std::string("invalid layout property: ")+key);
    return v->get<double>();
}
struct GuiBox {double x=0,y=0,width=0,height=0,rotation=0,scale=1;bool attached=false;};
struct GuiFlexSlot {
    double size=0,minimum=0,maximum=std::numeric_limits<double>::infinity(),grow=0,shrink=0;
};
// Distribute an amount from natural sizes, freezing capped items and sharing
// the remainder. Sorting cap/weight thresholds avoids quadratic rescans when
// many items hit different bounds. Normalize weights before summing them.
void gui_flex_distribute(std::vector<GuiFlexSlot>& slots,double delta) {
    if(!std::isfinite(delta))throw std::runtime_error("nonfinite flex space");
    const bool growing=delta>0;
    double maxWeight=0;
    for(const auto& slot:slots)maxWeight=std::max(maxWeight,growing?slot.grow:slot.shrink);
    if(delta==0||maxWeight==0)return;
    struct Share {size_t index;double weight,capacity,threshold;};
    std::vector<Share> shares;
    for(size_t i=0;i<slots.size();++i) {
        const auto& slot=slots[i];double weight=(growing?slot.grow:slot.shrink)/maxWeight;
        double capacity=growing?slot.maximum-slot.size:slot.size-slot.minimum;
        if(weight>0&&capacity>0)shares.push_back({i,weight,capacity,capacity/weight});
    }
    std::sort(shares.begin(),shares.end(),[](const Share& a,const Share& b){return a.threshold<b.threshold;});
    std::vector<double> suffixWeight(shares.size()+1,0);
    for(size_t i=shares.size();i>0;--i)suffixWeight[i-1]=suffixWeight[i]+shares[i-1].weight;
    double remaining=std::abs(delta);
    for(size_t i=0;i<shares.size();++i) {
        const auto& share=shares[i];
        const double totalWeight=suffixWeight[i];
        if(remaining<=0||totalWeight<=0)break;
        if(remaining*(share.weight/totalWeight)<=share.capacity) {
            for(size_t j=i;j<shares.size();++j) {
                auto& slot=slots[shares[j].index];
                double amount=std::min(shares[j].capacity,remaining*(shares[j].weight/totalWeight));
                slot.size=std::clamp(slot.size+(growing?amount:-amount),slot.minimum,slot.maximum);
            }
            break;
        }
        auto& slot=slots[share.index];slot.size=growing?slot.maximum:slot.minimum;
        remaining-=share.capacity;
    }
}
struct GuiLayoutPass {
    World& w;
    std::unordered_map<std::string,GuiBox> boxes;
    std::unordered_map<std::string,std::vector<Node*>> children;
    struct ContentLayout {
        double width=0,height=0,cell_width=0,cell_height=0,columns=0,rows=0;
        std::unordered_map<std::string,GuiBox> items;
    };
    std::unordered_map<std::string,ContentLayout> layouts;
    // A measuring pass supplies an unscrolled canvas for one container. Its
    // children can then use the ordinary box/list solvers without recursion.
    std::unordered_map<std::string,GuiBox> content_overrides;
    std::unordered_map<std::string,int> intrinsic_axes;
    struct AutomaticResult {std::array<double,7> key;double width,height;};
    struct MeasureState {
        size_t work=0;
        std::unordered_map<std::string,std::vector<AutomaticResult>> automatic;
    };
    std::shared_ptr<MeasureState> measure_state=std::make_shared<MeasureState>();
    int measure_depth=0;
    bool indexed=false;
    void index() {
        if(indexed)return;indexed=true;
        for(auto& id:w.order)if(auto* n=find_node(w,id);n&&!n->destroyed)children[parent_id(w,*n)].push_back(n);
    }
    Node* component(Node& n,const char* cls) {
        index();Node* found=nullptr;
        for(auto* child:children[n.id])if(child->class_name==cls) {
            if(found)throw std::runtime_error(std::string("multiple active GUI components are unsupported: ")+cls);
            found=child;
        }
        return found;
    }
    Node* layout_component(Node& n) {
        index();Node* result=nullptr;
        for(auto* child:children[n.id]) {
            const auto& cls=child->class_name;
            if(!class_is_a(w,cls,"UILayout"))continue;
            if(cls!="UIListLayout"&&cls!="UIGridLayout")throw std::runtime_error("GUI content layout is not implemented: "+cls);
            if(result)throw std::runtime_error("multiple active GUI components are unsupported: content layout");
            result=child;
        }
        return result;
    }
    ContentLayout& arrange(Node& layout,Node& container,const GuiBox& area,int depth) {
        if(auto it=layouts.find(layout.id);it!=layouts.end())return it->second;
        if(layout.class_name=="UIGridLayout")return grid(layout,container,area,depth);
        int direction=gui_enum_value(w,layout,"FillDirection");
        int horizontal=gui_enum_value(w,layout,"HorizontalAlignment");
        int vertical=gui_enum_value(w,layout,"VerticalAlignment");
        int sort=gui_enum_value(w,layout,"SortOrder");
        if(sort==1)throw std::runtime_error("custom GUI list sorting is not implemented");
        const auto* wraps=property_value(w,layout,"Wraps");
        if(!wraps||!wraps->is_boolean())throw std::runtime_error("invalid UIListLayout.Wraps");
        const int horizontalFlex=gui_enum_value(w,layout,"HorizontalFlex");
        const int verticalFlex=gui_enum_value(w,layout,"VerticalFlex");
        const int intrinsic=intrinsic_axes.count(container.id)?intrinsic_axes.at(container.id):0;
        const bool intrinsicMain=intrinsic&(direction==0?1:2);
        const int mainFlex=intrinsicMain?0:direction==0?horizontalFlex:verticalFlex;
        const int crossFlex=(intrinsic&(direction==0?2:1))?0:direction==0?verticalFlex:horizontalFlex;
        const int lineAlignment=gui_enum_value(w,layout,"ItemLineAlignment");
        const auto* padding=property_value(w,layout,"Padding");
        if(!padding)throw std::runtime_error("GUI list Padding unavailable");
        const double gap=dimension(*padding,direction==0?area.width:area.height,area.scale);
        struct Item {
            Node* node;GuiBox box;double order;uint64_t insertion;std::string name;
            std::array<double,2> minimum{0,0},maximum{std::numeric_limits<double>::infinity(),std::numeric_limits<double>::infinity()};
            double grow=0,shrink=0;int alignment=0;
        };
        std::vector<Item> items;
        for(auto* child:children[container.id]) {
            if(!gui_object(w,*child))continue;
            const auto* visible=property_value(w,*child,"Visible");
            if(!visible||!visible->is_boolean())throw std::runtime_error("GUI list child visibility unavailable");
            if(!visible->get<bool>())continue;
            auto order=w.gui_parent_order.find(child->id);
            Item item{child,box(*child,depth+1,true),layout_number(w,*child,"LayoutOrder",0),
                order==w.gui_parent_order.end()?0:order->second,instance_name(w,*child)};
            item.grow=item.shrink=mainFlex==1?1:0;item.alignment=lineAlignment;
            if(auto* flex=component(*child,"UIFlexItem")) {
                const int mode=gui_enum_value(w,*flex,"FlexMode");
                item.grow=mode==1||mode==3?1:mode==4?layout_number(w,*flex,"GrowRatio",0):0;
                item.shrink=mode==2||mode==3?1:mode==4?layout_number(w,*flex,"ShrinkRatio",0):0;
                if(item.grow<0||item.shrink<0)throw std::runtime_error("flex ratios must be nonnegative");
                int ownAlignment=gui_enum_value(w,*flex,"ItemLineAlignment");
                if(ownAlignment)item.alignment=ownAlignment;
            }
            // Automatic containers measure content before stretching it to
            // fill their own size, otherwise a zero-sized container can erase
            // every child's basis while attempting to discover that size.
            if(intrinsicMain)item.grow=item.shrink=0;
            if(item.alignment==0&&crossFlex!=0)item.alignment=4;
            if(auto* bounds=component(*child,"UISizeConstraint")) {
                item.minimum=gui_size_bound(*property_value(w,*bounds,"MinSize"),false);
                item.maximum=gui_size_bound(*property_value(w,*bounds,"MaxSize"),true);
                validate_gui_bounds(item.minimum,item.maximum);
                for(int axis=0;axis<2;++axis) {
                    item.minimum[axis]*=item.box.scale;
                    if(std::isfinite(item.maximum[axis]))item.maximum[axis]*=item.box.scale;
                }
            }
            if(item.box.scale==0)item.minimum=item.maximum={0,0};
            // An aspect constraint owns the natural size instead of allowing
            // flex to change one dimension and silently break its ratio.
            if(component(*child,"UIAspectRatioConstraint"))item.minimum=item.maximum={item.box.width,item.box.height};
            items.push_back(std::move(item));
        }
        std::stable_sort(items.begin(),items.end(),[&](const Item& a,const Item& b) {
            if(sort==0&&a.name!=b.name)return a.name<b.name;
            if(sort==2&&a.order!=b.order)return a.order<b.order;
            return a.insertion<b.insertion;
        });
        // Pack in sorted order using constrained natural sizes. An oversized
        // item owns one line; it must not generate an empty line before itself.
        struct Line {size_t begin=0,end=0;double cursor=0,low=0,high=0,cross=0,offset=0,gap=0,edge=0;};
        std::vector<Line> lines;
        Line line;
        const double available=direction==0?area.width:area.height;
        for(size_t i=0;i<items.size();++i) {
            const auto& b=items[i].box;
            const double size=direction==0?b.width:b.height;
            double at=line.cursor+(line.end>line.begin?gap:0);
            if(wraps->get<bool>()&&line.end>line.begin&&
               std::max(line.high,at+size)-std::min(line.low,at)>available) {
                lines.push_back(line);line=Line{};line.begin=line.end=i;at=0;
            }
            line.low=std::min(line.low,at);line.high=std::max(line.high,at+size);
            line.cross=std::max(line.cross,direction==0?b.height:b.width);
            line.cursor=at+size;line.end=i+1;
        }
        if(line.end>line.begin)lines.push_back(line);
        // Space distribution treats Padding as the minimum spacing, including
        // the half/full edge slots for Around/Evenly. Measure layout padding in
        // AbsoluteContentSize, independently of the overall alignment offset.
        struct Flow {double gap=0,edge=0,low=0,span=0;};
        auto flow=[&](const std::vector<double>& sizes,int mode,double extent) {
            Flow f;f.gap=gap;if(sizes.empty())return f;
            double sum=0;for(double size:sizes)sum+=size;
            if(mode>=2&&(mode!=3||sizes.size()>1)) {
                double slots=mode==2?sizes.size():mode==3?sizes.size()-1:sizes.size()+1;
                f.gap=std::max(gap,(extent-sum)/slots);
                f.edge=mode==2?f.gap/2:mode==4?f.gap:0;
            }
            double cursor=f.edge,high=0;
            for(double size:sizes) {
                f.low=std::min(f.low,cursor);high=std::max(high,cursor+size);cursor+=size+f.gap;
            }
            high=std::max(high,cursor-f.gap+f.edge);f.span=high-f.low;
            if(!std::isfinite(f.span))throw std::runtime_error("nonfinite GUI flex geometry");
            return f;
        };
        const int mainAxis=direction==0?0:1,crossAxis=1-mainAxis;
        std::vector<double> crossSizes;
        std::vector<GuiFlexSlot> crossSlots;
        for(auto& row:lines) {
            std::vector<GuiFlexSlot> slots;std::vector<double> sizes;
            double crossMinimum=0;
            for(size_t i=row.begin;i<row.end;++i) {
                auto& item=items[i];
                const double size=direction==0?item.box.width:item.box.height;
                slots.push_back({size,item.minimum[mainAxis],item.maximum[mainAxis],item.grow,item.shrink});
            }
            const double minimumEdges=mainFlex==2?gap:mainFlex==4?2*gap:0;
            gui_flex_distribute(slots,available-(row.high-row.low)-minimumEdges);
            row.cross=0;
            for(size_t i=row.begin;i<row.end;++i) {
                auto& item=items[i];double size=slots[i-row.begin].size;
                if(direction==0)item.box.width=size;else item.box.height=size;
                int automaticCross=gui_enum_value(w,*item.node,"AutomaticSize")&(direction==0?2:1);
                if(automaticCross) {
                    auto base=item.box;
                    base.rotation=0; // UIListLayout overrides authored rotation.
                    const double ownScale=area.scale>0?base.scale/area.scale:0;
                    const int constraint=gui_enum_value(w,*item.node,"SizeConstraint");
                    const auto* authored=property_value(w,*item.node,"Size");
                    const double extent=crossAxis==0?(constraint==2?area.height:area.width):
                        (constraint==1?area.width:area.height);
                    const double minimum=std::max(0.,dimension(authored->at("$udim2").at(crossAxis),extent,area.scale)*ownScale);
                    if(crossAxis==0)base.width=minimum;else base.height=minimum;
                    auto measured=automatic_box(*item.node,base,area,ownScale,automaticCross);
                    if(crossAxis==0)item.box.width=measured.width;else item.box.height=measured.height;
                    item.minimum[crossAxis]=std::max(item.minimum[crossAxis],crossAxis==0?measured.width:measured.height);
                }
                const double crossSize=direction==0?item.box.height:item.box.width;
                row.cross=std::max(row.cross,crossSize);
                crossMinimum=std::max(crossMinimum,item.alignment==4?item.minimum[crossAxis]:crossSize);
                sizes.push_back(size);
            }
            auto f=flow(sizes,mainFlex,available);
            row.low=f.low;row.high=f.low+f.span;row.gap=f.gap;row.edge=f.edge;
            crossSizes.push_back(row.cross);
            crossSlots.push_back({row.cross,crossMinimum,std::numeric_limits<double>::infinity(),1,1});
        }
        const double crossAvailable=direction==0?area.height:area.width;
        if(crossFlex==1) {
            auto basis=flow(crossSizes,0,crossAvailable);
            gui_flex_distribute(crossSlots,crossAvailable-basis.span);
            for(size_t i=0;i<lines.size();++i)crossSizes[i]=lines[i].cross=crossSlots[i].size;
        }
        const auto crossFlow=flow(crossSizes,crossFlex,crossAvailable);
        ContentLayout result;
        double main=0,crossCursor=crossFlow.edge;
        for(auto& row:lines) {
            row.offset=crossCursor;
            main=std::max(main,row.high-row.low);
            crossCursor+=row.cross+crossFlow.gap;
        }
        const double cross=crossFlow.span;
        result.width=direction==0?main:cross;result.height=direction==0?cross:main;
        auto align=[](int mode,double free){return mode==0?free/2:mode==2?free:0.;};
        const int crossAlignment=direction==0?vertical:horizontal;
        const double crossStart=align(crossAlignment,crossAvailable-cross)-crossFlow.low;
        for(const auto& row:lines) {
            double cursor=align(direction==0?horizontal:vertical,available-(row.high-row.low))-row.low+row.edge;
            for(size_t i=row.begin;i<row.end;++i) {
                auto& item=items[i];auto b=item.box;
                if(item.alignment==4) {
                    double stretched=std::clamp(row.cross,item.minimum[crossAxis],item.maximum[crossAxis]);
                    if(direction==0)b.height=stretched;else b.width=stretched;
                }
                const double free=row.cross-(direction==0?b.height:b.width);
                const double within=item.alignment==0?align(crossAlignment,free):
                    item.alignment==2?free/2:item.alignment==3?free:0.;
                const double across=crossStart+row.offset+within;
                b.x=area.x+(direction==0?cursor:across);
                b.y=area.y+(direction==1?cursor:across);
                b.rotation=0;
                if(!std::isfinite(b.x)||!std::isfinite(b.y)||!std::isfinite(b.width)||!std::isfinite(b.height))
                    throw std::runtime_error("nonfinite GUI list geometry");
                result.items.emplace(item.node->id,b);
                cursor+=(direction==0?b.width:b.height)+row.gap;
            }
        }
        return layouts.emplace(layout.id,std::move(result)).first->second;
    }
    ContentLayout& grid(Node& layout,Node& container,const GuiBox& area,int depth) {
        ContentLayout result;
        const auto* cell=property_value(w,layout,"CellSize");
        const auto* padding=property_value(w,layout,"CellPadding");
        if(!cell||!padding)throw std::runtime_error("grid cell geometry unavailable");
        const double cw=std::max(0.,dimension(cell->at("$udim2").at(0),area.width,area.scale));
        const double ch=std::max(0.,dimension(cell->at("$udim2").at(1),area.height,area.scale));
        const double px=dimension(padding->at("$udim2").at(0),area.width,area.scale);
        const double py=dimension(padding->at("$udim2").at(1),area.height,area.scale);
        if(!std::isfinite(cw+px)||!std::isfinite(ch+py))throw std::runtime_error("nonfinite grid cell stride");
        result.cell_width=cw;result.cell_height=ch;
        const int direction=gui_enum_value(w,layout,"FillDirection");
        const int corner=gui_enum_value(w,layout,"StartCorner");
        const int horizontal=gui_enum_value(w,layout,"HorizontalAlignment");
        const int vertical=gui_enum_value(w,layout,"VerticalAlignment");
        const int sort=gui_enum_value(w,layout,"SortOrder");
        if(sort==1)throw std::runtime_error("custom GUI grid sorting is not implemented");
        const double limit=layout_number(w,layout,"FillDirectionMaxCells",0);
        if(limit<0||limit>2147483647||std::floor(limit)!=limit)throw std::runtime_error("invalid FillDirectionMaxCells");
        struct Item {
            Node* node;GuiBox box;double order;uint64_t insertion;std::string name;
            uint64_t main=0,cross=0,main_span=1,cross_span=1;
        };
        std::vector<Item> items;
        GuiBox forced=area;forced.width=cw;forced.height=ch;
        uint64_t totalMain=0;
        for(auto* child:children[container.id]) {
            if(!gui_object(w,*child))continue;
            const auto* visible=property_value(w,*child,"Visible");
            if(!visible||!visible->is_boolean())throw std::runtime_error("GUI grid child visibility unavailable");
            if(!visible->get<bool>())continue;
            auto order=w.gui_parent_order.find(child->id);
            Item item{child,box(*child,depth+1,true,&forced),layout_number(w,*child,"LayoutOrder",0),
                order==w.gui_parent_order.end()?0:order->second,instance_name(w,*child)};
            if(auto* bounds=component(*child,"UISizeConstraint")) {
                auto minimum=gui_size_bound(*property_value(w,*bounds,"MinSize"),false);
                auto span=[](double required,double size,double gap) -> uint64_t {
                    if(required<=size)return 1;
                    if(size+gap<=0)throw std::runtime_error("grid spanning requires a positive cell stride");
                    double cells=std::max(1.,std::ceil((required+gap)/(size+gap)));
                    if(!std::isfinite(cells)||cells>1000000)throw std::runtime_error("grid cell span limit exceeded");
                    return uint64_t(cells);
                };
                // UIScale changes an item's display size, not the grid's cell
                // size. Minimum-size spans use container-scale cell units.
                uint64_t x=span(minimum[0]*area.scale,cw,px),y=span(minimum[1]*area.scale,ch,py);
                item.main_span=direction==0?x:y;item.cross_span=direction==0?y:x;
            }
            totalMain+=item.main_span;items.push_back(std::move(item));
        }
        std::stable_sort(items.begin(),items.end(),[&](const Item& a,const Item& b) {
            if(sort==0&&a.name!=b.name)return a.name<b.name;
            if(sort==2&&a.order!=b.order)return a.order<b.order;
            return a.insertion<b.insertion;
        });
        const double available=direction==0?area.width:area.height;
        const double cellMain=direction==0?cw:ch,padMain=direction==0?px:py;
        double fit=cellMain+padMain>0?std::floor((available+padMain)/(cellMain+padMain)):double(totalMain);
        uint64_t capacity=uint64_t(std::clamp(fit,1.,double(std::max(uint64_t(1),totalMain))));
        if(limit>0)capacity=std::min(capacity,uint64_t(limit));
        uint64_t main=0,cross=0,usedMain=0,usedCross=0;
        size_t work=0;
        for(size_t i=0;i<items.size();++i) {
            auto& item=items[i];
            for(;;) {
                if(main>0&&(main>=capacity||item.main_span>capacity-main)){main=0;++cross;}
                bool collided=false;
                for(size_t j=0;j<i;++j) {
                    if(++work>2000000)throw std::runtime_error("grid packing work limit exceeded");
                    const auto& previous=items[j];
                    if(main<previous.main+previous.main_span&&main+item.main_span>previous.main&&
                       cross<previous.cross+previous.cross_span&&cross+item.cross_span>previous.cross) {
                        if(previous.main==0&&previous.main_span>=capacity){main=0;cross=previous.cross+previous.cross_span;}
                        else main=previous.main+previous.main_span;
                        collided=true;break;
                    }
                }
                if(!collided)break;
            }
            item.main=main;item.cross=cross;
            usedMain=std::max(usedMain,main+item.main_span);usedCross=std::max(usedCross,cross+item.cross_span);
            main+=item.main_span;
        }
        const uint64_t columns=direction==0?usedMain:usedCross,rows=direction==0?usedCross:usedMain;
        result.columns=double(columns);result.rows=double(rows);
        auto bounds=[](uint64_t count,double size,double gap) {
            if(!count)return std::array<double,2>{0,0};
            double last=double(count-1)*(size+gap),low=std::min(0.,last),high=std::max(size,last+size);
            return std::array<double,2>{low,high};
        };
        auto xb=bounds(columns,cw,px),yb=bounds(rows,ch,py);
        result.width=xb[1]-xb[0];result.height=yb[1]-yb[0];
        auto align=[](int mode,double free){return mode==0?free/2:mode==2?free:0.;};
        const double startX=area.x+align(horizontal,area.width-result.width)-xb[0];
        const double startY=area.y+align(vertical,area.height-result.height)-yb[0];
        for(auto& item:items) {
            uint64_t x=direction==0?item.main:item.cross,y=direction==0?item.cross:item.main;
            const uint64_t xs=direction==0?item.main_span:item.cross_span,ys=direction==0?item.cross_span:item.main_span;
            if(corner&1)x=columns-x-xs;
            if(corner&2)y=rows-y-ys;
            auto b=item.box;b.x=startX+double(x)*(cw+px);b.y=startY+double(y)*(ch+py);b.rotation=0;
            if(!std::isfinite(b.x)||!std::isfinite(b.y)||!std::isfinite(result.width)||!std::isfinite(result.height))
                throw std::runtime_error("nonfinite GUI grid geometry");
            result.items.emplace(item.node->id,b);
        }
        return layouts.emplace(layout.id,std::move(result)).first->second;
    }
    double dimension(const Json& value,double extent,double scale) {
        const auto& a=value.at("$udim");
        if(!a.is_array()||a.size()!=2||!a[0].is_number()||!a[1].is_number())throw std::runtime_error("invalid GUI UDim");
        double result=a[0].get<double>()*extent+a[1].get<double>()*scale;
        if(!std::isfinite(result))throw std::runtime_error("nonfinite GUI layout");
        return result;
    }
    GuiBox constrain(Node& n,GuiBox b,const GuiBox& parent,double own_scale) {
        if(auto* bounds=component(n,"UISizeConstraint")) {
            if(component(n,"UIAspectRatioConstraint"))throw std::runtime_error("combined size and aspect constraints are not implemented");
            const auto* min=property_value(w,*bounds,"MinSize");
            const auto* max=property_value(w,*bounds,"MaxSize");
            if(!min||!max)throw std::runtime_error("size constraint bounds unavailable");
            auto minimum=gui_size_bound(*min,false),maximum=gui_size_bound(*max,true);
            validate_gui_bounds(minimum,maximum);
            // Constraints are authored in the same pixel coordinate system
            // as offsets. Apply cumulative UIScale to both finite bounds.
            auto clamp_axis=[&](double size,int axis) {
                if(b.scale==0)return 0.0;
                double lower=minimum[axis]*b.scale;
                double upper=std::isinf(maximum[axis])?maximum[axis]:maximum[axis]*b.scale;
                return std::max(lower,std::min(size,upper));
            };
            b.width=clamp_axis(b.width,0);b.height=clamp_axis(b.height,1);
        }
        if(auto* aspect=component(n,"UIAspectRatioConstraint")) {
            double ratio=layout_number(w,*aspect,"AspectRatio",1);
            if(ratio<=0)throw std::runtime_error("AspectRatio must be greater than zero");
            int mode=gui_enum_value(w,*aspect,"AspectType");
            int axis=gui_enum_value(w,*aspect,"DominantAxis");
            if(mode==1) {
                // ScaleWithParentSize derives the other dimension from
                // the authored dominant axis, bounded by the parent's
                // content box. UIScale magnifies the constrained result,
                // just as it magnifies authored offsets and size bounds.
                if(axis==0) {
                    b.width=std::min(b.width,parent.width*own_scale);
                    b.height=parent.height*own_scale;
                } else {
                    b.width=parent.width*own_scale;
                    b.height=std::min(b.height,parent.height*own_scale);
                }
            }
            // Fit the largest ratio-preserving rectangle inside the authored
            // or parent-bounded box before positioning its anchor or sizing
            // descendants. FitWithinMaxSize uses both authored dimensions.
            if(b.width==0||b.height==0)b.width=b.height=0;
            else if(b.width/b.height>ratio)b.width=b.height*ratio;
            else b.height=b.width/ratio;
        }
        return b;
    }
    GuiBox automatic_box(Node& n,const GuiBox& base,const GuiBox& parent,double own_scale,int automatic) {
        if(n.class_name!="Frame")throw std::runtime_error("automatic GUI sizing for this class is not implemented");
        const std::array<double,7> key{base.width,base.height,base.scale,parent.width,parent.height,own_scale,double(automatic)};
        if(auto found=measure_state->automatic.find(n.id);found!=measure_state->automatic.end())
            for(const auto& cached:found->second)if(cached.key==key) {
                auto result=base;result.width=cached.width;result.height=cached.height;return result;
            }
        auto candidate=constrain(n,base,parent,own_scale);
        for(int iteration=0;iteration<64;++iteration) {
            auto extent=measure_canvas(n,candidate,candidate,automatic);
            auto next=base;
            if(automatic&1)next.width=std::max(base.width,extent[0]);
            if(automatic&2)next.height=std::max(base.height,extent[1]);
            next=constrain(n,next,parent,own_scale);
            if(std::abs(next.width-candidate.width)<=1e-5&&std::abs(next.height-candidate.height)<=1e-5) {
                measure_state->automatic[n.id].push_back({key,next.width,next.height});
                return next;
            }
            candidate=next;
        }
        throw std::runtime_error("automatic GUI sizing did not converge; cyclic size dependency");
    }
    struct ScrollMetrics {
        GuiBox area;
        double canvas_width=0,canvas_height=0,window_width=0,window_height=0,x=0,y=0;
    };
    std::unordered_map<std::string,ScrollMetrics> scroll_layouts;
    std::array<double,2> measure_canvas(Node& n,const GuiBox& outer,const GuiBox& area,int intrinsic=0) {
        if(measure_depth>=64)throw std::runtime_error("automatic layout measurement depth limit exceeded");
        measure_state->work+=w.nodes.size();
        if(measure_state->work>1000000)throw std::runtime_error("automatic layout measurement work limit exceeded");
        GuiLayoutPass measure{w};
        measure.measure_state=measure_state;measure.measure_depth=measure_depth+1;
        measure.boxes[n.id]=outer;
        measure.content_overrides[n.id]=area;
        measure.intrinsic_axes[n.id]=intrinsic;
        measure.index();
        auto inner=measure.content(n,outer);
        double right=0,bottom=0;
        if(auto* padding=measure.component(n,"UIPadding")) {
            right=measure.dimension(*property_value(w,*padding,"PaddingRight"),area.width,area.scale);
            bottom=measure.dimension(*property_value(w,*padding,"PaddingBottom"),area.height,area.scale);
        }
        std::array<double,2> extent{inner.x-area.x,inner.y-area.y};
        if(auto* layout=measure.layout_component(n)) {
            auto& arranged=measure.arrange(*layout,n,inner,0);
            extent[0]+=arranged.width;extent[1]+=arranged.height;
        } else for(auto* child:measure.children[n.id]) {
            if(!gui_object(w,*child))continue;
            const auto* visible=property_value(w,*child,"Visible");
            if(!visible||!visible->is_boolean())throw std::runtime_error("automatic content visibility unavailable");
            if(!visible->get<bool>())continue;
            auto b=measure.box(*child,1);
            if(b.rotation!=0)throw std::runtime_error("automatic canvas sizing with rotated content is not implemented");
            extent[0]=std::max(extent[0],b.x-area.x+b.width);
            extent[1]=std::max(extent[1],b.y-area.y+b.height);
        }
        extent[0]=std::max(0.,extent[0]+right);extent[1]=std::max(0.,extent[1]+bottom);
        if(!std::isfinite(extent[0])||!std::isfinite(extent[1]))throw std::runtime_error("nonfinite automatic canvas extent");
        return extent;
    }
    ScrollMetrics scroll(Node& n,const GuiBox& outer,const Json* requested=nullptr) {
        ScrollMetrics result;result.area=outer;
        w.active_scroll_layouts.insert(n.id);
        if(!outer.attached)return result;
        const int automatic=gui_enum_value(w,n,"AutomaticCanvasSize");
        const auto* size=property_value(w,n,"CanvasSize");
        const auto* position=requested?requested:property_value(w,n,"CanvasPosition");
        const auto* enabled=property_value(w,n,"ScrollingEnabled");
        if(!size||!position||!enabled||!enabled->is_boolean())throw std::runtime_error("scrolling canvas properties unavailable");
        const auto& offsets=position->at("$vector2");
        if(!offsets.is_array()||offsets.size()!=2)throw std::runtime_error("invalid CanvasPosition");
        for(const auto& v:offsets)if(!v.is_number()||!std::isfinite(v.get<double>()))throw std::runtime_error("CanvasPosition must be finite");
        double thickness=layout_number(w,n,"ScrollBarThickness",12);
        if(thickness<0)throw std::runtime_error("ScrollBarThickness must be nonnegative");
        thickness*=outer.scale;
        const int direction=gui_enum_value(w,n,"ScrollingDirection");
        const int hInset=gui_enum_value(w,n,"HorizontalScrollBarInset");
        const int vInset=gui_enum_value(w,n,"VerticalScrollBarInset");
        const int side=gui_enum_value(w,n,"VerticalScrollBarPosition");
        const double width=std::max(0.,dimension(size->at("$udim2").at(0),outer.width,outer.scale));
        const double height=std::max(0.,dimension(size->at("$udim2").at(1),outer.height,outer.scale));
        const bool canH=enabled->get<bool>()&&direction!=1;
        const bool canV=enabled->get<bool>()&&direction!=0;
        bool horizontal=false,vertical=false;
        if(auto cached=scroll_layouts.find(n.id);cached!=scroll_layouts.end())result=cached->second;
        else {
            double expandedWidth=width,expandedHeight=height;
            bool converged=false;
            size_t work=0;
            for(int expansion=0;expansion<64;expansion++) {
                double insetX=0,insetY=0;
                horizontal=false;vertical=false;
                // A scrollbar can make the perpendicular axis overflow.
                for(int iteration=0;iteration<4;iteration++) {
                    insetX=(vInset==2||(vInset==1&&vertical))?thickness:0;
                    insetY=(hInset==2||(hInset==1&&horizontal))?thickness:0;
                    result.canvas_width=std::max(0.,expandedWidth-insetX);
                    result.canvas_height=std::max(0.,expandedHeight-insetY);
                    result.window_width=std::max(0.,outer.width-(vertical?thickness:0));
                    result.window_height=std::max(0.,outer.height-(horizontal?thickness:0));
                    bool nextH=canH&&result.canvas_width>result.window_width;
                    bool nextV=canV&&result.canvas_height>result.window_height;
                    if(nextH==horizontal&&nextV==vertical)break;
                    horizontal=nextH;vertical=nextV;
                }
                result.area=outer;
                result.area.x+=side==1?std::min(outer.width,insetX):0;
                result.area.width=std::max(result.canvas_width,std::max(0.,outer.width-insetX));
                result.area.height=std::max(result.canvas_height,std::max(0.,outer.height-insetY));
                if(!automatic){converged=true;break;}
                // Bound cyclic scale dependencies independently of VM slices:
                // this native layout loop must never spin indefinitely.
                work+=w.nodes.size();
                if(work>1000000)throw std::runtime_error("automatic canvas layout work limit exceeded");
                auto extent=measure_canvas(n,outer,result.area);
                double nextWidth=(automatic&1)?std::max(width,extent[0]+insetX):width;
                double nextHeight=(automatic&2)?std::max(height,extent[1]+insetY):height;
                if(std::abs(nextWidth-expandedWidth)<=1e-5&&std::abs(nextHeight-expandedHeight)<=1e-5) {
                    converged=true;break;
                }
                expandedWidth=nextWidth;expandedHeight=nextHeight;
            }
            if(!converged)throw std::runtime_error("automatic canvas layout did not converge; cyclic size dependency");
            scroll_layouts[n.id]=result;
        }
        horizontal=canH&&result.canvas_width>result.window_width;
        vertical=canV&&result.canvas_height>result.window_height;
        const double physicalX=horizontal?std::clamp(offsets[0].get<double>()*outer.scale,0.,std::max(0.,result.canvas_width-result.window_width)):0;
        const double physicalY=vertical?std::clamp(offsets[1].get<double>()*outer.scale,0.,std::max(0.,result.canvas_height-result.window_height)):0;
        if(outer.scale>0){result.x=physicalX/outer.scale;result.y=physicalY/outer.scale;}
        result.area.x-=physicalX;
        result.area.y-=physicalY;
        if(!requested) {
            Json normalized=display_vector(result.x,result.y);
            if(*position!=normalized)w.local_properties[n.id]["CanvasPosition"]=std::move(normalized);
        }
        return result;
    }
    GuiBox content(Node& n,GuiBox b) {
        if(auto override=content_overrides.find(n.id);override!=content_overrides.end())b=override->second;
        else if(n.class_name=="ScrollingFrame")b=scroll(n,b).area;
        if(auto* padding=component(n,"UIPadding")) {
            double left=dimension(*property_value(w,*padding,"PaddingLeft"),b.width,b.scale);
            double right=dimension(*property_value(w,*padding,"PaddingRight"),b.width,b.scale);
            double top=dimension(*property_value(w,*padding,"PaddingTop"),b.height,b.scale);
            double bottom=dimension(*property_value(w,*padding,"PaddingBottom"),b.height,b.scale);
            b.x+=left;b.y+=top;b.width=std::max(0.0,b.width-left-right);b.height=std::max(0.0,b.height-top-bottom);
        }
        return b;
    }
    GuiBox box(Node& n,int depth=0,bool natural=false,const GuiBox* forced=nullptr) {
        if(depth>128)throw std::runtime_error("GUI ancestry exceeds layout depth limit");
        if(!natural)if(auto it=boxes.find(n.id);it!=boxes.end())return it->second;
        GuiBox b;
        if(n.destroyed)return b;
        if(n.class_name=="ScreenGui"||n.id==w.overlay_root) {
            auto* parent=find_node(w,parent_id(w,n));int hops=0;
            while(parent&&parent->class_name!="PlayerGui"&&parent->class_name!="CoreGui"&&parent->id!=w.overlay_root&&++hops<=128)
                parent=find_node(w,parent_id(w,*parent));
            if((!parent&&n.id!=w.overlay_root)||hops>128) {
                // A ScreenGui detached from PlayerGui/CoreGui still reports
                // Studio's default 800x600 surface at the origin; GUI insets
                // do not apply to that detached surface.
                b.attached=true;b.width=800;b.height=600;
                if(!natural)boxes[n.id]=b;return b;
            }
            b.attached=w.display["size"][0].get<double>()>0&&w.display["size"][1].get<double>()>0;
            int mode=2;
            const auto* explicit_mode=property_value(w,n,"ScreenInsets");
            if(explicit_mode) {
                if(!explicit_mode->is_number_integer())throw std::runtime_error("unsupported ScreenInsets encoding");
                mode=explicit_mode->get<int>();
            } else if(const auto* ignore=property_value(w,n,"IgnoreGuiInset")) {
                if(!ignore->is_boolean())throw std::runtime_error("invalid IgnoreGuiInset");
                if(ignore->get<bool>())mode=1;
            }
            Json margins=Json::array({0,0,0,0});
            if(mode==1)margins=w.display["device_insets"];
            else if(mode==2)margins=w.display["core_insets"];
            else if(mode==3) {
                if(!w.display.contains("topbar_insets"))throw std::runtime_error("TopbarSafeInsets requires host topbar area");
                margins=w.display["topbar_insets"];
            } else if(mode!=0)throw std::runtime_error("unknown ScreenInsets value");
            b.x=margins[0].get<double>()-w.display["core_insets"][0].get<double>();
            b.y=margins[1].get<double>()-w.display["core_insets"][1].get<double>();
            b.width=w.display["size"][0].get<double>()-margins[0].get<double>()-margins[2].get<double>();
            b.height=w.display["size"][1].get<double>()-margins[1].get<double>()-margins[3].get<double>();
        } else if(gui_object(w,n)) {
            auto* p=find_node(w,parent_id(w,n));
            if(!p)return b;
            if(p->class_name!="ScreenGui"&&p->id!=w.overlay_root&&!gui_object(w,*p))throw std::runtime_error("GUI parent has no supported layout surface");
            auto parent=box(*p,depth+1);
            if(!parent.attached)return b;
            if(parent.rotation!=0)throw std::runtime_error("rotated ancestor layout is not implemented");
            int automatic=gui_enum_value(w,n,"AutomaticSize");
            int constraint=gui_enum_value(w,n,"SizeConstraint");
            index();
            // A layout belongs to a container's contents, not its outer box.
            // Size constraints belong to the individual object being sized.
            Node* layout=layout_component(*p);
            for(auto* child:children[n.id]) {
                const auto& cls=child->class_name;
                if(cls!="UITextSizeConstraint"&&cls!="UIAspectRatioConstraint"&&cls!="UISizeConstraint"&&class_is_a(w,cls,"UIConstraint"))
                    throw std::runtime_error("GUI size constraint is not implemented: "+cls);
            }
            if(gui_object(w,*p))parent=content(*p,parent);
            if(layout&&layout->class_name=="UIGridLayout"&&!natural) {
                auto& arranged=arrange(*layout,*p,parent,depth);
                if(auto it=arranged.items.find(n.id);it!=arranged.items.end()){boxes[n.id]=it->second;return it->second;}
            }
            const auto* size=property_value(w,n,"Size");const auto* position=property_value(w,n,"Position");
            if((!size&&!forced)||!position)throw std::runtime_error("GUI Size or Position unavailable in snapshot");
            double ax=0,ay=0;
            if(const auto* anchor=property_value(w,n,"AnchorPoint")) {
                const auto& a=anchor->at("$vector2");ax=a.at(0).get<double>();ay=a.at(1).get<double>();
                if(!std::isfinite(ax)||!std::isfinite(ay))throw std::runtime_error("invalid GUI AnchorPoint");
            }
            double own_scale=1;
            if(auto* scale=component(n,"UIScale"))own_scale=layout_number(w,*scale,"Scale",1);
            if(own_scale<0)throw std::runtime_error("negative UIScale is unsupported");
            b.scale=parent.scale*own_scale;b.attached=true;
            if(forced){b.width=forced->width*own_scale;b.height=forced->height*own_scale;}
            else {
                b.width=std::max(0.0,dimension(size->at("$udim2").at(0),constraint==2?parent.height:parent.width,parent.scale)*own_scale);
                b.height=std::max(0.0,dimension(size->at("$udim2").at(1),constraint==1?parent.width:parent.height,parent.scale)*own_scale);
            }
            if(automatic&&!forced)b=automatic_box(n,b,parent,own_scale,automatic);
            else b=constrain(n,b,parent,own_scale);
            b.x=parent.x+dimension(position->at("$udim2").at(0),parent.width,parent.scale)-ax*b.width;
            b.y=parent.y+dimension(position->at("$udim2").at(1),parent.height,parent.scale)-ay*b.height;
            b.rotation=layout_number(w,n,"Rotation",0);
            if(layout&&!natural) {
                auto& arranged=arrange(*layout,*p,parent,depth);
                if(auto it=arranged.items.find(n.id);it!=arranged.items.end())b=it->second;
            }
            if(!std::isfinite(b.x)||!std::isfinite(b.y)||!std::isfinite(b.width)||!std::isfinite(b.height)||!std::isfinite(b.scale))
                throw std::runtime_error("nonfinite GUI geometry");
        } else throw std::runtime_error("unsupported GUI layout class");
        if(!natural)boxes[n.id]=b;return b;
    }
    Json value(Node& n,const std::string& key) {
        if((n.class_name=="UIListLayout"||n.class_name=="UIGridLayout")&&display_property(w,n,key)) {
            auto* parent=find_node(w,parent_id(w,n));
            if(!parent)return display_vector(0,0);
            auto area=box(*parent);
            if(!area.attached)return display_vector(0,0);
            if(layout_component(*parent)!=&n)throw std::runtime_error("inactive GUI content layout");
            if(gui_object(w,*parent))area=content(*parent,area);
            auto& result=arrange(n,*parent,area,0);
            if(key=="AbsoluteCellSize")return display_vector(result.cell_width,result.cell_height);
            if(key=="AbsoluteCellCount")return display_vector(result.columns,result.rows);
            return display_vector(result.width,result.height);
        }
        auto b=box(n);
        if(n.class_name=="ScrollingFrame"&&(key=="AbsoluteCanvasSize"||key=="AbsoluteWindowSize"||key=="CanvasPosition")) {
            auto metrics=scroll(n,b);
            if(key=="AbsoluteCanvasSize")return display_vector(metrics.canvas_width,metrics.canvas_height);
            if(key=="AbsoluteWindowSize")return display_vector(metrics.window_width,metrics.window_height);
            return display_vector(metrics.x,metrics.y);
        }
        if(key=="AbsoluteSize")return display_vector(b.width,b.height);
        if(key=="AbsolutePosition")return display_vector(b.x,b.y);
        return b.rotation;
    }
};
void watch_display_property(World& w,Node& n,const std::string& key) {
    if(!display_property(w,n,key))return;
    auto& watched=w.display_watches[n.id];
    if(watched.contains(key))return;
    try{GuiLayoutPass pass{w};watched[key]=pass.value(n,key);}catch(const std::exception&){watched[key]=nullptr;}
}
bool surface_visible(World& w,Node& n) {
    Node* current=&n;
    for(int depth=0;current&&depth<128;++depth) {
        if(current->destroyed)return false;
        if(current->id==w.overlay_root)return true;
        for(const char* key:{"Visible","Enabled"})
            if(const auto* value=property_value(w,*current,key);value&&value->is_boolean()&&!value->get<bool>())return false;
        if(current->class_name=="CoreGui")return true;
        if(current->class_name=="PlayerGui")return parent_id(w,*current)==w.local_player;
        current=find_node(w,parent_id(w,*current));
    }
    return false;
}
void refresh_display_events(World& w) {
    GuiLayoutPass pass{w};
    // Retire overscroll on a resize even when no signal is connected. Preserve
    // the clamped position, rather than reviving an old request on later growth.
    std::vector<std::string> scrollers(w.active_scroll_layouts.begin(),w.active_scroll_layouts.end());
    for(const auto& id:scrollers) {
        auto* n=find_node(w,id);
        if(!n||n->destroyed){w.active_scroll_layouts.erase(id);continue;}
        try{pass.scroll(*n,pass.box(*n));}catch(const std::exception&){}
    }
    for(auto it=w.display_watches.begin();it!=w.display_watches.end();) {
        auto* n=find_node(w,it->first);
        if(!n||n->destroyed){it=w.display_watches.erase(it);continue;}
        for(auto p=it->second.begin();p!=it->second.end();++p) {
            Json current;
            try{current=pass.value(*n,p.key());}catch(const std::exception&){current=nullptr;}
            if(current!=p.value()){p.value()=current;property_events(w,*n,p.key());}
        }
        ++it;
    }
}
int gui_apply_layout(lua_State* L) {
    auto* h=checked_handle(L,1);
    if(h->node->class_name!="UIListLayout"&&h->node->class_name!="UIGridLayout") {
        luaL_error(L,"ApplyLayout requires UIListLayout or UIGridLayout");return 0;
    }
    try {
        GuiLayoutPass pass{*h->world};pass.value(*h->node,"AbsoluteContentSize");
        refresh_display_events(*h->world);
    } catch(const std::exception& e){luaL_error(L,"ApplyLayout failed: %s",e.what());return 0;}
    return 0;
}
int gui_get_inset(lua_State* L) {
    auto* h=checked_handle(L,1);
    if(h->node->class_name!="GuiService"){luaL_error(L,"GetGuiInset requires GuiService");return 0;}
    const auto& m=h->world->display["core_insets"];
    push_json(L,*h->world,display_vector(m[0].get<double>(),m[1].get<double>()));
    push_json(L,*h->world,display_vector(m[2].get<double>(),m[3].get<double>()));return 2;
}
