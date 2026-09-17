#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include "kernels.hpp"
namespace py=pybind11;
using Array=py::array;
// No forcecast: byte order, strides, dtype, alignment and dimensions are checked
// before accessing a pointer. The Python adapter owns immutable call snapshots.
template<class T> const T* checked(const Array& a,int ndim) {
    if(!a.dtype().is(py::dtype::of<T>()) || a.ndim()!=ndim || !(a.flags()&Array::c_style)
       || reinterpret_cast<std::uintptr_t>(a.data())%alignof(T))
        throw std::invalid_argument("Expected aligned native-endian C-contiguous typed array");
    for(int i=0;i<ndim;++i) if(a.strides(i)<0) throw std::invalid_argument("Negative strides unsupported");
    py::object owner = py::reinterpret_borrow<py::object>(a);
    while(py::isinstance<Array>(owner)) {
        owner = py::reinterpret_borrow<Array>(owner).attr("base");
    }
    if(!py::isinstance<py::bytes>(owner))
        throw std::invalid_argument("Native inputs require immutable bytes ownership; use preparation adapter");
    ginseng::product(static_cast<std::size_t>(a.size()),sizeof(T));
    return static_cast<const T*>(a.data());
}
PYBIND11_MODULE(_core,m) {
    m.def("build_info",[]{
        py::dict d; d["api_version"]=1; d["source_hash"]=GINSENG_SOURCE_HASH; d["kernel_hash"]=GINSENG_KERNEL_HASH;
#ifdef __VERSION__
        d["compiler"]=__VERSION__;
#else
        d["compiler"]="MSVC";
#endif
        d["cmake_hash"]=GINSENG_CMAKE_HASH; d["package_hash"]=GINSENG_PACKAGE_HASH;
        d["build_type"]=GINSENG_BUILD_TYPE; d["environment_compiler_flags"]=GINSENG_COMPILER_FLAGS;
        d["options"]="C++20; no fast-math; no FP contraction; portable target";
        return d;
    });
    m.def("evaluate",[](const Array& history,const Array& indices,const Array& direct,const Array& schedule,
                         py::ssize_t horizon,py::ssize_t start,py::ssize_t stop,double opening,double buffer,bool full,bool historical) {
        auto hp=checked<double>(history,2); auto ip=checked<std::int64_t>(indices,2);
        auto dp=checked<double>(direct,2); auto sp=checked<double>(schedule,1);
        const auto& source=historical ? indices : direct;
        auto n=source.shape(0), material=source.shape(1);
        if(n<1 || material<1 || horizon<1 || horizon>material || start<0 || stop<=start || stop>n
           || schedule.shape(0)!=material || history.shape(1)!=3 || !std::isfinite(opening) || !std::isfinite(buffer))
            throw std::invalid_argument("Invalid dimensions, row range, horizon or policy");
        ginseng::product(ginseng::product(stop-start,horizon),sizeof(double));
        // Validate all inputs before output allocation; called once per block.
        // Immutable snapshots held by caller cannot race with GIL-free access.
        ginseng::finite(hp,history.size()); ginseng::finite(sp,schedule.size());
        if(historical) {
            for(auto j=start;j<stop;++j) for(py::ssize_t t=0;t<material;++t)
                if(ip[j*material+t]<0 || ip[j*material+t]>=history.shape(0)) throw std::invalid_argument("Out-of-range index");
        } else ginseng::finite(dp+start*material,(stop-start)*material);
        py::array_t<double> paths(full ? std::vector<py::ssize_t>{stop-start,horizon}:std::vector<py::ssize_t>{0,0});
        py::array_t<double> stats(std::vector<py::ssize_t>{stop-start,6});
        double* xp=full ? paths.mutable_data():nullptr; double* out=stats.mutable_data();
        auto rows=history.shape(0);
        { py::gil_scoped_release release;
          ginseng::evaluate(hp,rows,ip,dp,sp,material,horizon,start,stop,opening,buffer,historical,xp,out); }
        return py::make_tuple(full ? py::object(paths):py::none(),stats);
    },py::arg("history").noconvert(),py::arg("indices").noconvert(),py::arg("direct").noconvert(),py::arg("schedule").noconvert(),
       py::arg("horizon"),py::arg("start"),py::arg("stop"),py::arg("opening"),py::arg("buffer"),py::arg("full"),py::arg("historical"));
    m.def("quantiles",[](const Array& values,const Array& weights,const Array& qs){
        auto x=checked<double>(values,1), w=checked<double>(weights,1), q=checked<double>(qs,1);
        auto n=values.size(), nq=qs.size();
        if(n<1 || weights.size()!=n) throw std::invalid_argument("Invalid weights shape");
        py::array_t<double> output(nq); auto out=output.mutable_data();
        { py::gil_scoped_release release; auto result=ginseng::quantiles(x,w,n,q,nq); std::copy(result.begin(),result.end(),out); }
        return output;
    },py::arg("values").noconvert(),py::arg("weights").noconvert(),py::arg("qs").noconvert());
    m.def("charts",[](const Array& matrix,const Array& weights,const Array& qs,double opening){
        auto x=checked<double>(matrix,2), w=checked<double>(weights,1), q=checked<double>(qs,1);
        auto n=matrix.shape(0),h=matrix.shape(1),nq=qs.size();
        if(n<1 || h<1 || weights.size()!=n || !std::isfinite(opening)) throw std::invalid_argument("Invalid chart shape or opening cash");
        py::array_t<double> output(std::vector<py::ssize_t>{nq,h}); auto out=output.mutable_data();
        { py::gil_scoped_release release;
          std::vector<double> column(n);
          for(py::ssize_t t=0;t<h;++t) {
              for(py::ssize_t j=0;j<n;++j) column[j]=x[j*h+t]+opening;
              auto result=ginseng::quantiles(column.data(),w,n,q,nq);
              for(py::ssize_t k=0;k<nq;++k) out[k*h+t]=result[k];
          }
        }
        return output;
    },py::arg("matrix").noconvert(),py::arg("weights").noconvert(),py::arg("qs").noconvert(),py::arg("opening"));
}
