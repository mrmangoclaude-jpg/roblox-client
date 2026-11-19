// Primitive mass and rigid assembly queries, evaluated from current state.
// Contracts: https://create.roblox.com/docs/reference/engine/classes/BasePart
#include "material_densities.inc"
bool part_mass_key(const std::string& key) {
    return key=="Mass"||key=="CenterOfMass"||key=="AssemblyMass"||key=="AssemblyCenterOfMass";
}
const Json* part_mass_default(World& w,const Node& n,const std::string& key) {
    if(n.server_owned||(key!="Material"&&key!="Shape")||!pivot_part(w,n))return nullptr;
    static const Json plastic=256,block=1;
    if(key=="Material")return &plastic;
    return class_is_a(w,n.class_name,"Part")?&block:nullptr;
}
// Avoid derived origins here: a constructor's stored zero center is not a
// measurement, even when the public getter now computes a nonzero center.
const Json* explicit_part_value(World& w,const Node& n,const char* key) {
    if(const auto* v=local_value(w,n,key))return v;
    if(n.properties.contains(key)) {
        auto it=n.origins.find(key);
        if(it==n.origins.end()||*it!="class_default")return &n.properties[key];
        return nullptr;
    }
    auto origins=w.default_origins.find(n.class_name);
    if(origins!=w.default_origins.end()&&origins->contains(key)&&(*origins)[key]!="class_default")
        return property_value(w,n,key);
    return nullptr;
}
int part_mass_enum(World& w,const Node& n,const char* key,const char* type) {
    auto* v=property_value(w,n,key);
    if(v&&v->is_object()&&v->contains("$enum")) {
        const auto& e=(*v)["$enum"];
        if(!e.is_object()||e.value("type","")!=type||!e.contains("value"))throw std::runtime_error("invalid part enum type");
        v=&e["value"];
    }
    if(!v||!v->is_number_integer())throw std::runtime_error(std::string(key)+" is unavailable");
    return v->get<int>();
}
int part_primitive_shape(World& w,const Node& n) {
    if(n.class_name=="WedgePart")return 3;
    if(n.class_name=="CornerWedgePart")return 4;
    if(n.class_name=="VehicleSeat")return 1;
    if(class_is_a(w,n.class_name,"Part"))return part_mass_enum(w,n,"Shape","PartType");
    throw std::runtime_error("mass geometry is unavailable for "+n.class_name);
}
FrameVector part_mass_size(World& w,const Node& n) {
    const auto* v=property_value(w,n,"Size");if(!v)throw std::runtime_error("Size is unavailable");
    auto size=part_vector(*v);
    for(double x:size)if(x<=0)throw std::runtime_error("mass geometry requires positive Size");
    return size;
}
double part_density(World& w,const Node& n) {
    const auto* custom=property_value(w,n,"CustomPhysicalProperties");
    if(custom&&!custom->is_null()) {
        const auto* fields=custom;
        if(custom->is_object()&&custom->contains("$physical_properties"))fields=&(*custom)["$physical_properties"];
        if(!fields->is_array()||fields->size()<5||fields->size()>6||!(*fields)[0].is_number())
            throw std::runtime_error("invalid custom density");
        double density=(*fields)[0].get<double>();
        if(!std::isfinite(density))throw std::runtime_error("invalid custom density");
        return std::clamp(density,0.0001,100.0);
    }
    if(const auto* variant=property_value(w,n,"MaterialVariant");variant&&(!variant->is_string()||!variant->get<std::string>().empty()))
        throw std::runtime_error("MaterialVariant density is unavailable");
    int material=part_mass_enum(w,n,"Material","Material");
    for(const auto& item:kMaterialDensities)if(item.value==material)return item.density;
    throw std::runtime_error("material density is unavailable");
}
bool part_mass_geometry_authored(World& w,const Node& n,bool center=false) {
    for(const char* key:{"Size","Shape"})if(local_value(w,n,key))return true;
    if(!center)for(const char* key:{"Material","MaterialVariant","CustomPhysicalProperties"})
        if(local_value(w,n,key))return true;
    return false;
}

bool assembly_mass_authored(World& w,Node& n,const std::string& key) {
    const bool center=key=="AssemblyCenterOfMass";
    std::unordered_set<std::string> affected,parent_changes;
    for(const auto& id:w.order) {
        Node* node=find_node(w,id);if(!node)continue;
        if(local_value(w,*node,"Parent"))parent_changes.insert(id);
        if(pivot_part(w,*node)) {
            if(part_mass_geometry_authored(w,*node)||local_value(w,*node,"Massless")||
               local_value(w,*node,"Anchored")||local_value(w,*node,"RootPriority")||
               (center&&local_value(w,*node,"CFrame")))affected.insert(id);
        }
        if(!joint_rigid(*node))continue;
        bool changed=!node->server_owned||w.locally_destroyed.count(id);
        for(const char* field:{"Part0","Part1","Enabled","Parent"})if(local_value(w,*node,field))changed=true;
        std::unordered_set<std::string> ancestors;
        for(Node* ancestor=node;ancestor&&ancestors.insert(ancestor->id).second;
            ancestor=find_node(w,parent_id(w,*ancestor)))
            if(local_value(w,*ancestor,"Parent"))changed=true;
        std::vector<std::string> endpoints;
        for(const char* field:{"Part0","Part1"}) {
            auto remember=[&](const Json* ref) {
                if(ref&&ref->is_object()&&ref->contains("$ref")&&(*ref)["$ref"].is_string()) {
                    const auto target=(*ref)["$ref"].get<std::string>();endpoints.push_back(target);
                    if(w.locally_destroyed.count(target))changed=true;
                }
            };
            remember(property_value(w,*node,field));
            auto old=node->properties.find(field);if(old!=node->properties.end())remember(&*old);
        }
        if(changed)affected.insert(endpoints.begin(),endpoints.end());
    }
    if(affected.empty()&&parent_changes.empty())return false;
    // Invalidation may inspect an incomplete received graph. Follow potential
    // connections without demanding their missing state; only a relevant edit
    // makes the public query require a fully resolvable assembly.
    JointGraph graph(w);std::vector<Node*> members{&n};
    std::unordered_set<std::string> visited{n.id};
    for(size_t i=0;i<members.size();++i)for(auto index:graph.incident[members[i]->id]) {
        const auto& edge=graph.edges[index];
        if(!edge.rigid||(!edge.active&&edge.unknown.empty()))continue;
        auto* other=edge.a==members[i]?edge.b:edge.a;
        if(other&&visited.insert(other->id).second)members.push_back(other);
    }
    for(auto* member:members) {
        if(affected.count(member->id))return true;
        std::unordered_set<std::string> seen;
        while(member&&seen.insert(member->id).second) {
            if(parent_changes.count(member->id))return true;
            member=find_node(w,parent_id(w,*member));
        }
    }
    return false;
}

bool part_mass_authored(World& w,Node& n,const std::string& key) {
    if(!n.server_owned)return true;
    if(key=="Mass"||key=="CenterOfMass")return part_mass_geometry_authored(w,n,key=="CenterOfMass");
    return assembly_mass_authored(w,n,key);
}

double part_mass(World& w,Node& n) {
    if(n.server_owned&&!part_mass_geometry_authored(w,n)) {
        const auto* v=explicit_part_value(w,n,"Mass");
        if(!v||!v->is_number()||!std::isfinite(v->get<double>())||v->get<double>()<=0)
            throw std::runtime_error("received Mass is unavailable");
        return v->get<double>();
    }
    auto size=part_mass_size(w,n);int shape=part_primitive_shape(w,n);
    double volume=size[0]*size[1]*size[2];
    // Round primitives keep circular cross sections even with uneven Size.
    // https://devforum.roblox.com/t/improvements-to-part-shape-size/2443389
    if(shape==0){double d=std::min({size[0],size[1],size[2]});volume=d*d*d*std::acos(-1.0)/6;}
    else if(shape==2){double d=std::min(size[1],size[2]);volume=size[0]*d*d*std::acos(-1.0)/4;}
    else if(shape==3)volume*=.5;
    else if(shape==4)volume/=3;
    else if(shape!=1)throw std::runtime_error("unknown primitive shape");
    double mass=volume*part_density(w,n);
    if(!std::isfinite(mass)||mass>std::numeric_limits<float>::max())throw std::runtime_error("Mass exceeds finite range");
    return mass;
}
FrameVector part_local_center(World& w,Node& n) {
    if(n.server_owned&&!part_mass_geometry_authored(w,n,true)) {
        const auto* value=explicit_part_value(w,n,"CenterOfMass");
        if(!value)throw std::runtime_error("received center of mass is unavailable");
        return part_vector(*value);
    }
    int shape=part_primitive_shape(w,n);auto size=part_mass_size(w,n);
    if(shape==3)return {0,-size[1]/6,size[2]/6};
    if(shape==4)return {size[0]/8,-size[1]/4,-size[2]/8};
    if(shape<0||shape>4)throw std::runtime_error("unknown primitive shape");
    return {0,0,0};
}
FrameVector part_world_center(World& w,Node& n) {
    auto local=part_local_center(w,n);auto cf=pivot_frame(w,n,"CFrame");
    // A symmetric primitive's center needs only a position, not a rotation.
    if(local==FrameVector{0,0,0})return cf.p;
    if(!cf.rotation_known)throw std::runtime_error("center of mass rotation is unavailable");
    FrameVector center=cf.p;
    for(int i=0;i<3;++i)for(int j=0;j<3;++j)center[i]+=cf.r[i*3+j]*local[j];
    return center;
}
bool part_mass_flag(World& w,Node& n,const char* key) {
    const auto* value=property_value(w,n,key);
    if(!value||!value->is_boolean())throw std::runtime_error(std::string(key)+" is unavailable");
    return value->get<bool>();
}
Json part_mass_value(World& w,Node& n,const std::string& key) {
    if(n.destroyed)throw std::runtime_error("part is destroyed");
    if(n.server_owned&&!part_mass_authored(w,n,key)) {
        const auto* value=explicit_part_value(w,n,key.c_str());
        if(!value)throw std::runtime_error(key+" is unavailable in received state");
        if(key=="CenterOfMass"||key=="AssemblyCenterOfMass")part_vector(*value);
        else {double number=json_number(*value);if(std::isnan(number)||number<=0||(key=="Mass"&&!std::isfinite(number)))throw std::runtime_error("invalid received mass");}
        return *value;
    }
    if(key=="Mass")return part_mass(w,n);
    if(key=="CenterOfMass")return Json{{"$vector3",part_local_center(w,n)}};
    JointGraph graph(w);auto members=graph.connected(n,true);members.push_back(&n);
    Node* root=assembly_root(w,n,graph);if(!root)root=&n;
    for(auto* member:members)if(part_mass_flag(w,*member,"Anchored")) {
        if(key=="AssemblyMass")return encode_number(INFINITY);
        return Json{{"$vector3",part_world_center(w,*member)}};
    }
    double total=0;FrameVector weighted{0,0,0};
    for(auto* member:members) {
        if(member!=root&&part_mass_flag(w,*member,"Massless"))continue;
        double mass=part_mass(w,*member);total+=mass;
        if(key=="AssemblyCenterOfMass") {
            auto center=part_world_center(w,*member);
            for(int i=0;i<3;++i)weighted[i]+=mass*center[i];
        }
    }
    if(!std::isfinite(total)||total<=0||total>std::numeric_limits<float>::max())throw std::runtime_error("assembly mass exceeds finite range");
    if(key=="AssemblyMass")return total;
    for(double& value:weighted){value/=total;if(!std::isfinite(value)||std::abs(value)>std::numeric_limits<float>::max())throw std::runtime_error("assembly center exceeds finite range");}
    return Json{{"$vector3",weighted}};
}
std::string part_mass_origin(World& w,const Node& n,const std::string& key) {
    if(!part_mass_key(key)||!pivot_part(w,n))return {};
    try{auto& part=const_cast<Node&>(n);if(!part_mass_authored(w,part,key))return {};
        part_mass_value(w,part,key);return "local";}
    catch(const std::exception&){return "unavailable";}
}
int part_get_mass(lua_State* L) {
    auto* h=checked_handle(L,1);
    if(h->node->destroyed||!pivot_part(*h->world,*h->node)){luaL_error(L,"GetMass requires a live BasePart");return 0;}
    try{lua_pushnumber(L,part_mass(*h->world,*h->node));return 1;}
    catch(const std::exception& e){luaL_error(L,"GetMass: %s",e.what());return 0;}
}
bool part_mass_index(lua_State* L,World& w,Node& n,const std::string& key) {
    if(!pivot_part(w,n))return false;
    if(key=="GetMass"||key=="getMass"){lua_pushcfunction(L,part_get_mass,"GetMass");return true;}
    if(part_mass_key(key)){push_json(L,w,part_mass_value(w,n,key));return true;}
    if(key=="Shape"&&class_is_a(w,n.class_name,"Part")) {
        int value=part_mass_enum(w,n,"Shape","PartType");if(value<0||value>4)throw std::runtime_error("invalid PartType");
        push_geometry_item(L,kPartType,value);return true;
    }
    if(key=="Material") {
        int value=part_mass_enum(w,n,"Material","Material");
        if(!push_ussi_export_enum_json(L,Json{{"$enum",{{"type","Material"},{"value",value}}}}))throw std::runtime_error("Material enum is unavailable");
        return true;
    }
    return false;
}
bool part_mass_enum_write(lua_State* L,World& w,Node& n,const std::string& key) {
    if(!pivot_part(w,n)||(key!="Material"&&!(key=="Shape"&&class_is_a(w,n.class_name,"Part"))))return false;
    if(n.destroyed)throw std::runtime_error("part is destroyed");
    Json value;
    if(key=="Shape") {if(!capture_geometry_enum(L,3,value)||value["$enum"].value("type","")!="PartType")throw std::runtime_error("Shape requires Enum.PartType");}
    else if(!capture_ussi_export_enum(L,3,value)||value["$enum"].value("type","")!="Material")throw std::runtime_error("Material requires Enum.Material");
    const auto* old=property_value(w,n,key);bool changed=!old||*old!=value;
    std::vector<Json> entries{Json{{"kind","set"},{"id",n.id},{"property",key},{"value",value}}};
    check_mutation_budget(w,entries);w.local_properties[n.id][key]=value;append_mutations(w,std::move(entries));
    if(changed)property_events(w,n,key);return true;
}
Json observed_part_mass(World& w,Node& n,const std::string& key) {
    try{return part_mass_value(w,n,key);}
    catch(const std::exception&){return Json{{"unavailable",true}};}
}
void watch_part_mass(World& w,Node& n,const std::string& key) {
    if(!pivot_part(w,n)||(!part_mass_key(key)&&key!="Changed"))return;
    for(const char* property:{"Mass","CenterOfMass","AssemblyMass","AssemblyCenterOfMass"}) {
        if(key!="Changed"&&key!=property)continue;
        auto& watched=w.part_mass_watches[n.id];
        if(!watched.contains(property))watched[property]=observed_part_mass(w,n,property);
    }
}
void refresh_part_mass_events(World& w) {
    for(auto it=w.part_mass_watches.begin();it!=w.part_mass_watches.end();) {
        auto* n=find_node(w,it->first);
        if(!n||n->destroyed){it=w.part_mass_watches.erase(it);continue;}
        for(auto property=it->second.begin();property!=it->second.end();++property) {
            auto value=observed_part_mass(w,*n,property.key());
            if(value!=property.value()){property.value()=value;property_events(w,*n,property.key());}
        }
        ++it;
    }
}
