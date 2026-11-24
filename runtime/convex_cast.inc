// Distance and contact witnesses for a translating convex shape. The simplex
// stores both sides of the Minkowski difference so the hit stays on the target.
FrameVector cast_add_scaled(FrameVector a,const FrameVector& b,double scale) {
    for(int i=0;i<3;++i)a[i]+=b[i]*scale;
    return a;
}
double cast_length(const FrameVector& v){return std::hypot(v[0],v[1],v[2]);}
struct CastVertex {FrameVector delta,target;};
struct CastSimplex {
    std::array<CastVertex,4> vertices;
    int count=0;
};
struct CastWitness {FrameVector delta,target;double distance;};
constexpr double kCastContactTolerance=1e-7;

bool cast_affine_weights(const CastSimplex& simplex,const std::array<int,4>& indices,
                         int count,std::array<double,4>& weights) {
    const auto& origin=simplex.vertices[indices[0]].delta;
    std::array<FrameVector,3> basis{};
    double upper[3][3]{},rhs[3]{};
    // QR avoids squaring the condition number of a thin simplex.
    for(int column=0;column<count-1;++column) {
        const auto edge=query_subtract(simplex.vertices[indices[column+1]].delta,origin);
        auto residual=edge;
        for(int row=0;row<column;++row) {
            upper[row][column]=query_dot(basis[row],residual);
            residual=cast_add_scaled(residual,basis[row],-upper[row][column]);
        }
        upper[column][column]=cast_length(residual);
        if(upper[column][column]<=cast_length(edge)*1e-14)return false;
        for(double& v:residual)v/=upper[column][column];
        basis[column]=residual;
        rhs[column]=-query_dot(residual,origin);
    }
    weights[0]=1;
    for(int row=count-2;row>=0;--row) {
        double value=rhs[row];
        for(int column=row+1;column<count-1;++column)value-=upper[row][column]*weights[column+1];
        weights[row+1]=value/upper[row][row];
        weights[0]-=weights[row+1];
    }
    double total=0;
    for(int i=0;i<count;++i) {
        if(weights[i]<-1e-12)return false;
        weights[i]=std::max(0.0,weights[i]);total+=weights[i];
    }
    for(int i=0;i<count;++i)weights[i]/=total;
    return true;
}

CastWitness cast_reduce_simplex(CastSimplex& simplex) {
    CastWitness best{{},{},std::numeric_limits<double>::infinity()};
    CastSimplex reduced;
    for(int mask=1;mask<(1<<simplex.count);++mask) {
        std::array<int,4> indices{};
        int count=0;
        for(int i=0;i<simplex.count;++i)if(mask&(1<<i))indices[count++]=i;
        std::array<double,4> weights{};
        if(!cast_affine_weights(simplex,indices,count,weights))continue;
        FrameVector delta{},target{};
        for(int i=0;i<count;++i) {
            const auto& vertex=simplex.vertices[indices[i]];
            delta=cast_add_scaled(delta,vertex.delta,weights[i]);
            target=cast_add_scaled(target,vertex.target,weights[i]);
        }
        const double distance=cast_length(delta);
        if(distance>=best.distance)continue;
        best={delta,target,distance};reduced.count=0;
        for(int i=0;i<count;++i)if(weights[i]>0)reduced.vertices[reduced.count++]=simplex.vertices[indices[i]];
    }
    simplex=reduced;
    return best;
}

template<typename Support>
CastWitness cast_convex_distance(Support support,size_t& work) {
    CastSimplex simplex;
    simplex.vertices[simplex.count++]=support({1,0,0});
    for(int i=0;i<256;++i) {
        query_work(work,16);
        const auto closest=cast_reduce_simplex(simplex);
        if(closest.distance<=kCastContactTolerance)return closest;
        auto normal=closest.delta;
        for(double& v:normal)v/=closest.distance;
        const auto next=support({-normal[0],-normal[1],-normal[2]});
        const double gap=query_dot(next.delta,normal);
        if(closest.distance-gap<=1e-10*std::max(1.0,closest.distance))return closest;
        if(simplex.count==4)throw std::runtime_error("convex cast simplex did not converge");
        simplex.vertices[simplex.count++]=next;
    }
    throw std::runtime_error("convex cast distance did not converge");
}

struct ConvexContact {double distance;FrameVector point,normal;};
template<typename MovingSupport,typename TargetSupport>
std::optional<ConvexContact> cast_convex(const FrameVector& direction,double limit,
        MovingSupport moving,TargetSupport target,size_t& work) {
    double travel=0;
    FrameVector previous_normal{};
    for(int i=0;i<256;++i) {
        auto support=[&](const FrameVector& axis) {
            const auto target_point=target(FrameVector{-axis[0],-axis[1],-axis[2]});
            return CastVertex{query_subtract(cast_add_scaled(moving(axis),direction,travel),target_point),target_point};
        };
        const auto closest=cast_convex_distance(support,work);
        if(closest.distance<=kCastContactTolerance)return ConvexContact{travel,closest.target,previous_normal};
        auto normal=closest.delta;
        for(double& v:normal)v/=closest.distance;
        const double closing=-query_dot(normal,direction);
        if(closing<=0)return std::nullopt;
        // This plane separates the two shapes. Its gap gives a lower bound
        // on how far the moving shape must travel before contact is possible.
        const double gap=query_dot(support({-normal[0],-normal[1],-normal[2]}).delta,normal);
        if(travel==limit)return std::nullopt;
        const double estimated=travel+gap/closing;
        if(estimated-limit>1e-10*std::max(1.0,limit))return std::nullopt;
        const double next=std::min(estimated,limit);
        if(next<=travel)throw std::runtime_error("convex cast could not advance");
        travel=next;previous_normal=normal;
    }
    throw std::runtime_error("convex cast contact did not converge");
}
