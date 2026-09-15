#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>
namespace ginseng {
inline std::size_t product(std::size_t a, std::size_t b) {
    if (b && a > std::numeric_limits<std::size_t>::max()/b) throw std::overflow_error("Array size overflow");
    return a*b;
}
inline void finite(const double* p, std::size_t n) {
    for(std::size_t i=0;i<n;++i) if(!std::isfinite(p[i])) throw std::invalid_argument("Non-finite array");
}
inline void evaluate(const double* history, std::size_t history_rows, const std::int64_t* indices,
                     const double* direct, const double* schedule, std::size_t material,
                     std::size_t horizon, std::size_t start, std::size_t stop,
                     double opening, double buffer, bool historical, double* paths, double* stats) {
    for(std::size_t j=start;j<stop;++j) {
        double sum=0, minimum=std::numeric_limits<double>::infinity(), low=minimum, below=0, over=0;
        for(std::size_t t=0;t<horizon;++t) {
            double daily;
            if(historical) {
                auto k=indices[j*material+t];
                if(k<0 || static_cast<std::size_t>(k)>=history_rows) throw std::invalid_argument("Out-of-range index");
                daily=((history[k*3]-history[k*3+1])-history[k*3+2])+schedule[t];
            } else daily=direct[j*material+t]-schedule[t];
            sum+=daily;
            double balance=opening+sum;
            minimum=std::min(minimum,sum); low=std::min(low,balance);
            below+=std::max(0.,buffer-balance); over+=std::max(0.,-balance);
            if(paths) paths[(j-start)*horizon+t]=sum;
        }
        double* out=stats+(j-start)*6;
        out[0]=minimum; out[1]=sum; out[2]=low; out[3]=std::max(0.,-low); out[4]=below; out[5]=over;
        finite(out,6);
    }
}
inline std::vector<double> quantiles(const double* x, const double* weights, std::size_t n,
                                      const double* qs, std::size_t nq) {
    struct Entry { double value, weight; };
    std::vector<Entry> ordered; ordered.reserve(n);
    for(std::size_t i=0;i<n;++i) {
        if(!std::isfinite(x[i]) || !std::isfinite(weights[i]) || weights[i]<0) throw std::invalid_argument("Invalid value or weight");
        if(weights[i]>0) ordered.push_back({x[i],weights[i]});
    }
    if(ordered.empty()) throw std::invalid_argument("Weights need positive mass");
    std::stable_sort(ordered.begin(),ordered.end(),[](const Entry& a,const Entry& b){return a.value<b.value;});
    std::vector<long double> cumulative; cumulative.reserve(ordered.size());
    long double mass=0;
    for(auto e:ordered) { mass+=static_cast<long double>(e.weight); cumulative.push_back(mass); }
    std::vector<double> cdf; cdf.reserve(cumulative.size());
    for(auto c:cumulative) cdf.push_back(static_cast<double>(c/mass));
    std::vector<double> result; result.reserve(nq);
    for(std::size_t i=0;i<nq;++i) {
        if(!std::isfinite(qs[i]) || qs[i]<0 || qs[i]>1) throw std::invalid_argument("Invalid quantile");
        auto k=qs[i]==1 ? ordered.size()-1 : static_cast<std::size_t>(std::lower_bound(cdf.begin(),cdf.end(),qs[i])-cdf.begin());
        result.push_back(ordered[std::min(k,ordered.size()-1)].value);
    }
    return result;
}
}
