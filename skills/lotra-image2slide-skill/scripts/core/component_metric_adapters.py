"""Typed source-coordinate geometric measurements for trials and saved renders."""
import math
import numpy as np
from scipy.ndimage import convolve,distance_transform_edt
from scipy.spatial import cKDTree

GENERIC={'ssim','ssim_loss','boundary_f1','clarity_first','clarity_second','clarity_ratio',
         'color_histogram_tv','raw_hard_color_histogram_tv','mean_absolute_rgb_error',
         'boundary_distance_mean','boundary_distance_p95','boundary_distance_max'}
GEOMETRIC={'keypoint_distance','endpoint_distance','centerline_distance','curve_distance','line_width_error'}


def validate_metrics(row):
    for metric in row.get('metrics',[]):
        if not metric.get('applicable',True):continue
        spec=metric.get('measurement',{});adapter=spec.get('adapter',metric['id'])
        if adapter=='spatial_constraint':
            if (spec.get('channel') not in ('anchors','footprints','relations') or not spec.get('target') or
                    not spec.get('spatial_basis') or not spec.get('source_evidence') or metric.get('measurement_domain')!='analytic'):
                raise ValueError('Original-bound typed spatial constraint metric required')
            continue
        from .surface_metrics import validate as validate_surface
        if validate_surface(metric): continue
        if not spec and metric['id'] in GENERIC:continue
        if adapter not in GEOMETRIC:raise ValueError('Unsupported metric producer: '+metric['id'])
        if metric.get('unit')!='source_px' or spec.get('coordinate_space')!='component_roi' or not spec.get('source_evidence'):
            raise ValueError('Geometric measurements require independent original ROI coordinates and source_px units')
        window=spec.get('window')
        if not isinstance(window,list) or len(window)!=4 or min(window[:2])<0 or min(window[2:])<=0:
            raise ValueError('Freeze a nonempty source measurement window')
        if spec.get('statistic','max') not in ('mean','p95','max'):raise ValueError('Unsupported geometric statistic')
        if adapter=='line_width_error':
            if spec.get('width_estimator')!='pixel_cell_normal_chord':raise ValueError('Use the same pixel-cell chord estimator on independent source and candidate pixels')
        elif adapter=='keypoint_distance':
            locators=spec.get('keypoints',[])
            if not locators or len(locators)>64:raise ValueError('Named corresponding original keypoint locators required')
            for locator in locators:
                if not locator.get('id') or locator.get('kind') not in ('corner','intersection','endpoint') or len(locator.get('source_point',[]))!=2 or len(locator.get('window',[]))!=4:
                    raise ValueError('Freeze a typed keypoint identity, source coordinate and search window')
                if locator['kind']=='corner' and not (0<locator.get('sigma',0)<=3 and type(locator.get('min_distance')) is int and 1<=locator['min_distance']<=16 and 0<locator.get('threshold_rel',0)<=1):
                    raise ValueError('Freeze bounded corner detector parameters from the original')
        else:
            points=spec.get('source_points',[])
            if not points or len(points)>4096 or any(len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in points):
                raise ValueError('Finite independently observed source points required')
            if adapter=='endpoint_distance':
                count=spec.get('expected_count',len(points))
                if type(count) is not int or count!=len(points):
                    raise ValueError('Endpoint count must equal the complete independent source point set')
        if spec.get('foreground',{}).get('mode') not in ('dark','color'):
            raise ValueError('Freeze a dark/color foreground selector before observing candidates')
        foreground=spec['foreground'];limit=foreground.get('threshold')
        if type(limit) not in (int,float) or not 0<limit<=1:raise ValueError('Source-derived normalized foreground threshold required')
        if foreground['mode']=='color':
            color=foreground.get('rgb')
            if not isinstance(color,list) or len(color)!=3 or any(type(v) not in (int,float) or not 0<=v<=1 for v in color):raise ValueError('Normalized source RGB required')


def geometric(actual,component,support=None,source=None):
    from skimage.morphology import skeletonize
    source_pixels=source
    result={}
    for metric in component.get('metrics',[]):
        spec=metric.get('measurement')
        if not spec or not metric.get('applicable',True):continue
        adapter=spec.get('adapter',metric['id'])
        from .surface_metrics import UNITS, measure as measure_surface
        if adapter in UNITS:
            result[metric['id']] = measure_surface(source_pixels,actual,metric) if source_pixels is not None else {'valid':False,'reason':'Independent original pixels required'}
            continue
        x,y,w,h=spec['window']
        left,top=math.floor(x),math.floor(y);right,bottom=math.ceil(x+w),math.ceil(y+h)
        if left<0 or top<0 or right>actual.shape[1] or bottom>actual.shape[0]:
            result[metric['id']]={'valid':False,'reason':'Original measurement window outside ROI'};continue
        pixels=actual[top:bottom,left:right];fg=spec['foreground']
        from .component_features import foreground,keypoints,widths
        ink=foreground(pixels,fg)
        if support is not None:ink &= support[top:bottom,left:right]
        if not ink.any():result[metric['id']]={'valid':False,'reason':'No foreground in the frozen original window'};continue
        skeleton=skeletonize(ink)
        if adapter=='keypoint_distance':
            try:
                located=keypoints(ink,skeleton,spec,left,top)
                original_points=np.asarray([v['source_point'] for v in spec['keypoints']],float)
                distance=np.linalg.norm(located-original_points,axis=1)
            except ValueError as error:
                result[metric['id']]={'valid':False,'reason':str(error)};continue
            statistic=spec.get('statistic','max')
            value=float(np.mean(distance) if statistic=='mean' else np.percentile(distance,95) if statistic=='p95' else np.max(distance))
            result[metric['id']]={'valid':True,'value':value,'unit':'source_px','adapter':adapter,'correspondence':[v['id'] for v in spec['keypoints']],'candidate_alignment':False}
            continue
        elif adapter=='endpoint_distance':
            features=skeleton&(convolve(skeleton.astype(int),np.ones((3,3),int),mode='constant')==2)
        else:features=skeleton
        yy,xx=np.nonzero(features);points=np.column_stack((xx+left+.5,yy+top+.5))
        if not len(points):result[metric['id']]={'valid':False,'reason':'Declared feature absent'};continue
        if adapter=='line_width_error':
            if source_pixels is None:
                result[metric['id']]={'valid':False,'reason':'Independent source pixels required for width measurement'};continue
            source_ink=foreground(source_pixels[top:bottom,left:right],fg)
            if support is not None:source_ink &= support[top:bottom,left:right]
            try:
                measured=widths(ink,skeleton);expected=widths(source_ink,skeletonize(source_ink))
                quantiles=np.linspace(0,1,129)
                distance=np.abs(np.quantile(measured,quantiles)-np.quantile(expected,quantiles))
            except ValueError as error:
                result[metric['id']]={'valid':False,'reason':str(error)};continue
        else:
            source=np.asarray(spec['source_points'],float)
            if adapter in ('centerline_distance','curve_distance'):
                samples=[]
                for start,end in zip(source[:-1],source[1:]):
                    count=min(4096,max(2,math.ceil(np.linalg.norm(end-start)*4)+1))
                    samples.append(np.linspace(start,end,count))
                source=np.concatenate(samples) if samples else source
            if adapter=='endpoint_distance' and (len(points)!=len(source) or
                    len(source)!=spec.get('expected_count',len(source))):
                result[metric['id']]={'valid':False,'reason':'Endpoint topology differs from the source count'};continue
            if adapter=='endpoint_distance':
                from scipy.optimize import linear_sum_assignment
                matrix=np.linalg.norm(source[:,None,:]-points[None,:,:],axis=2)
                i,j=linear_sum_assignment(matrix);distance=matrix[i,j]
                if len(i)!=len(source) or len(j)!=len(points):
                    result[metric['id']]={'valid':False,'reason':'Incomplete endpoint correspondence'};continue
            else:distance=cKDTree(points).query(source)[0]
            if adapter in ('centerline_distance','curve_distance'):
                distance=np.concatenate((distance,cKDTree(source).query(points)[0]))
        statistic=spec.get('statistic','max')
        value=float(np.mean(distance) if statistic=='mean' else np.percentile(distance,95) if statistic=='p95' else np.max(distance))
        result[metric['id']]={'valid':math.isfinite(value),'value':value,'unit':'source_px','adapter':adapter,
                              'coordinate_space':'component_roi','candidate_alignment':False}
    return result
