"""Corresponding geometric features and a common pixel-cell width estimator."""
import math
import numpy as np
from scipy.ndimage import convolve, label, map_coordinates


def foreground(pixels,spec):
    return (pixels@np.array([.2126,.7152,.0722]) < spec['threshold'] if spec['mode']=='dark'
            else np.linalg.norm(pixels-np.asarray(spec['rgb']),axis=2) <= spec['threshold'])


def keypoints(ink,skeleton,spec,left,top):
    from skimage.feature import corner_harris,corner_peaks
    result=[];ids=set()
    for locator in spec['keypoints']:
        if locator['id'] in ids:raise ValueError('Distinct source feature identities required')
        ids.add(locator['id']);x,y,w,h=locator['window']
        l,t=math.floor(x-left),math.floor(y-top);r,b=math.ceil(x+w-left),math.ceil(y+h-top)
        if l<0 or t<0 or r>ink.shape[1] or b>ink.shape[0]:raise ValueError('Keypoint locator escaped frozen measurement window')
        if locator['kind']=='corner':
            response=corner_harris(ink.astype(float),method='k',k=.04,sigma=locator['sigma'])
            points=corner_peaks(response[t:b,l:r],min_distance=locator['min_distance'],
                                threshold_rel=locator['threshold_rel'],exclude_border=False)
            points=np.asarray([[p[1]+l+.5,p[0]+t+.5] for p in points],float)
        else:
            degree=convolve(skeleton.astype(int),np.ones((3,3),int),mode='constant')-skeleton
            features=skeleton & (degree>=3 if locator['kind']=='intersection' else degree==1)
            labels,count=label(features[t:b,l:r],structure=np.ones((3,3)))
            points=[]
            for index in range(1,count+1):
                yy,xx=np.nonzero(labels==index);points.append([float(xx.mean()+l+.5),float(yy.mean()+t+.5)])
            points=np.asarray(points,float)
        if len(points)!=1:raise ValueError('Ambiguous or absent corresponding '+locator['kind']+': '+locator['id'])
        point=points[0]+np.array([left,top])
        if any(np.linalg.norm(point-prior)<.5 for prior in result):raise ValueError('Two source keypoints mapped to one candidate feature')
        result.append(point)
    return np.asarray(result)


def widths(ink,skeleton):
    """PCA normal chords through pixel cells; identical source/candidate definition."""
    yy,xx=np.nonzero(skeleton)
    all_points=np.column_stack((xx,yy)).astype(float)
    degree=convolve(skeleton.astype(int),np.ones((3,3),int),mode='constant')-skeleton
    result=[];maximum=min(512,max(ink.shape)*2)
    distances=np.arange(0,maximum+.125,.125)
    padded=np.pad(ink.astype(float),1)
    for x,y in all_points:
        if degree[int(y),int(x)]!=2:continue
        near=all_points[np.linalg.norm(all_points-[x,y],axis=1)<=3]
        if len(near)<3:continue
        covariance=np.cov(near.T);_,vectors=np.linalg.eigh(covariance)
        normal=vectors[:,0];chords=[]
        for direction in (-1,1):
            points=np.array([x+1,y+1])+distances[:,None]*normal*direction
            samples=map_coordinates(padded,[points[:,1],points[:,0]],order=1,mode='constant',cval=0)
            outside=np.flatnonzero(samples<.5)
            if not len(outside):break
            index=int(outside[0])
            if index==0:break
            a,b=samples[index-1:index+1]
            chords.append(float(distances[index-1]+.125*(a-.5)/(a-b)))
        if len(chords)==2:result.append(sum(chords))
    if not result:raise ValueError('No unambiguous interior stroke supports the declared width estimator')
    return np.asarray(result)
