#include "kernels.hpp"
#include <cassert>
#include <random>
int main() {
    std::mt19937 rng(20260915);
    for(int trial=0;trial<1000;++trial) {
        std::size_t n=1+rng()%35,h=1+rng()%65,k=1+rng()%37;
        std::vector<double> history(k*3),schedule(h),out(n*h),stats(n*6),weights(n,1.0/n),qs{0,.1,.5,.9,1};
        std::vector<std::int64_t> indices(n*h);
        for(auto& v:history) v=static_cast<int>(rng()%200)-100;
        for(auto& v:indices) v=rng()%k;
        ginseng::evaluate(history.data(),k,indices.data(),nullptr,schedule.data(),h,h,0,n,0,10,true,out.data(),stats.data());
        auto quantiles=ginseng::quantiles(stats.data(),weights.data(),n,qs.data(),qs.size());
        assert(quantiles.front()<=quantiles.back());
        indices.back()=k;
        bool caught=false;
        try { ginseng::evaluate(history.data(),k,indices.data(),nullptr,schedule.data(),h,h,0,n,0,10,true,nullptr,stats.data()); }
        catch(const std::invalid_argument&) {caught=true;}
        assert(caught);
    }
    bool overflow=false;
    try {ginseng::product(std::numeric_limits<std::size_t>::max(),2);} catch(const std::overflow_error&) {overflow=true;}
    assert(overflow);
}
