"""Source-confirmed two-wave antenna as compact native analytic contours."""
import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr
from skimage.measure import find_contours, approximate_polygon


def fit_radio(rgb, owned, paint, background, family):
    if family.get('wave_count') != 2 or family.get('central_mast') is not True or not family.get('source_evidence'):
        raise ValueError('Source must independently confirm two open waves and central mast')
    data = np.asarray(rgb, float)
    mask = np.asarray(owned, bool)
    h, w = mask.shape
    if min(h, w) < 12 or mask.sum() < 40:
        raise ValueError('Read a complete sufficiently observable original radial glyph')
    if mask[[0, -1], :].any() or mask[:, [0, -1]].any():
        raise ValueError('Original support reaches the ROI edge: read exterior context and correct source extent first')
    backgrounds, fg = np.asarray(background, float), np.asarray(paint, float)
    if backgrounds.ndim==1:backgrounds=backgrounds[None,:]
    if backgrounds.ndim!=2 or backgrounds.shape[1]!=3 or not 1<=len(backgrounds)<=12:
        raise ValueError('Declare bounded independently observed background planes')
    delta = fg-backgrounds
    norms=np.sum(delta**2,axis=1)
    if np.min(norms) < 2500:
        raise ValueError('Need independently observed foreground/background paint')
    candidates=np.clip(np.sum((data[:,:,None,:]-backgrounds)*delta,axis=3)/norms,0,1)
    deviations=np.linalg.norm(data[:,:,None,:]-(backgrounds+candidates[:,:,:,None]*delta),axis=3)
    closest=deviations.argmin(axis=2)
    alpha=np.take_along_axis(candidates,closest[:,:,None],axis=2)[:,:,0]
    off_axis=np.take_along_axis(deviations,closest[:,:,None],axis=2)[:,:,0]
    # Original antialiasing can mix more than one nearby background plane.
    # Fit confident colour samples; preserve every independently owned source
    # sample as a one-sided geometry constraint instead of changing its mask.
    domain = (off_axis <= 24) & ((alpha <= .10) | mask)
    uncertain=mask & ~domain
    if np.count_nonzero(domain & mask)<40:
        raise ValueError('Insufficient confident original radial paint; retain source ambiguity')
    yy, xx = np.indices((h, w), dtype=float)
    xx += .5
    yy += .5
    tail = mask & (yy > h*.60) & (alpha > .4)
    if tail.sum() < 8:
        raise ValueError('Original lower mast/base is not independently visible')
    cx = float(np.average(xx[tail], weights=alpha[tail]))
    ys, xs = np.where(mask)
    cy = h*.43
    rx = (xs.max()-xs.min()+1)/2-1
    ry = cy-ys.min()-1
    # The wide lower bar owns its own source evidence. A percentile of all
    # wave/head pixels may cut off this small important part entirely.
    lower = tail & (yy >= float(yy[tail].max())-1.01)
    if lower.sum() < 6:
        raise ValueError('Original rounded lower base is insufficiently observed')
    base = float(np.average(yy[lower],weights=alpha[lower]))
    base_evidence = {'source_lower_rows':[float(yy[lower].min()),float(yy[lower].max())],
                     'source_lower_samples':int(lower.sum()),'initial_base_y':base,
                     'basis':'independently owned bottom mast/base, never whole-glyph percentile'}
    p0 = np.array([cx,cy,rx,ry,rx*.60,ry*.63,2.,2.,145.,cy,3.,3.4,1.9,base,2.,1.8,.75])
    lo = np.array([cx-1.5,cy-3,rx-2,ry-3,rx*.43,ry*.45,1.,1.,125.,cy-2,2.,2.4,1.,base-1.5,1.2,1.,.2])
    hi = np.array([cx+1.5,cy+3,rx+2,ry+3,rx*.78,ry*.82,3.3,3.3,165.,cy+3,4.5,4.7,3.,base+1.5,3.5,3.,1.5])

    def ellipse_distance(x, y, ex, ey, erx, ery):
        u, v = (x-ex)/erx, (y-ey)/ery
        r = np.maximum(np.hypot(u, v), 1e-9)
        norm = np.hypot(u/erx, v/ery)/r
        return (r-1)/np.maximum(norm, 1e-6)

    def arc_distance(x, y, ex, ey, erx, ery, width, start):
        theta = np.mod(np.degrees(np.arctan2((y-ey)/ery,(x-ex)/erx)),360)
        on_arc = (theta >= start) | (theta <= 180-start)
        radial = np.abs(ellipse_distance(x,y,ex,ey,erx,ery))
        angle = np.radians(start)
        left = (ex+erx*np.cos(angle),ey+ery*np.sin(angle))
        right = (ex-erx*np.cos(angle),left[1])
        tip = np.minimum(np.hypot(x-left[0],y-left[1]),np.hypot(x-right[0],y-right[1]))
        return np.where(on_arc,radial,tip)-width/2

    def field(p, x, y):
        ex,ey,orx,ory,irx,iry,ow,iw,start,hcy,hrx,hry,sw,by,bh,bw,_ = p
        outer = arc_distance(x,y,ex,ey,orx,ory,ow,start)
        inner = arc_distance(x,y,ex,ey,irx,iry,iw,start)
        head = ellipse_distance(x,y,ex,hcy,hrx,hry)
        stem_top = hcy+hry*.5
        stem = np.hypot(x-ex,y-np.clip(y,stem_top,by))-sw/2
        base = np.hypot(x-np.clip(x,ex-bh,ex+bh),y-by)-bw/2
        return np.minimum.reduce([outer,inner,head,stem,base])

    def residual(p):
        proposed = ndtr(-field(p,xx,yy)/p[-1])
        colour=(proposed-alpha)[domain].ravel()
        support=np.minimum(0,proposed[uncertain]-.35)
        return np.concatenate([colour,support])

    solution = least_squares(residual,p0,bounds=(lo,hi),loss='soft_l1',f_scale=.12,max_nfev=160,x_scale='jac')
    p = solution.x
    if not np.isfinite(p).all() or p[2] <= p[4]+1 or p[3] <= p[5]+1:
        raise ValueError('Original fit does not support distinct concentric waves')
    resolution = 8
    hy, hx = np.indices((h*resolution,w*resolution),dtype=float)
    hx, hy = (hx+.5)/resolution, (hy+.5)/resolution
    scalar = ndtr(-field(p,hx,hy)*resolution)
    contours = []
    for raw in find_contours(np.pad(scalar,1),.5):
        if len(raw) < 6:
            continue
        points = approximate_polygon((raw-.5)/resolution,.045)
        xy = [[float(c)/w,float(r)/h] for r,c in points]
        if np.allclose(xy[0],xy[-1]):
            xy.pop()
        commands = [{'op':'moveTo','points':[xy[0]]}]
        for i, start in enumerate(xy):
            prev, end, follow = xy[(i-1)%len(xy)],xy[(i+1)%len(xy)],xy[(i+2)%len(xy)]
            c1 = [start[k]+(end[k]-prev[k])*.12 for k in (0,1)]
            c2 = [end[k]-(follow[k]-start[k])*.12 for k in (0,1)]
            commands.append({'op':'cubicBezTo','points':[c1,c2,end]})
        commands.append({'op':'close','points':[]})
        contours.append({'closed':True,'commands':commands})
    if len(contours) != 3:
        raise ValueError('Complete native radio must retain two separate open waves and its connected mast/base')
    audit = {'family':'two_open_radial_waves_and_mast','parameters':p.tolist(),'parameter_names':['cx','cy','outer_rx','outer_ry','inner_rx','inner_ry','outer_width','inner_width','start_angle_deg','head_cy','head_rx','head_ry','stem_width','base_y','base_half_width','base_width','source_blur_sigma'], 'original_owned_samples':int(mask.sum()),'source_background_planes':backgrounds.tolist(),'base_prior':base_evidence,'uncertain_mixed_background_samples':int(uncertain.sum()),'source_field_rms':float(np.sqrt(np.mean(residual(p)**2))), 'source_inference':'Regular analytic curves fitted to the observed original glyph; source blur is estimated, the native output is clear. No new scientific content.', 'limits':'Source-fit residual is proposal evidence, not saved Office drawing acceptance; own fixed metrics, semantic observation and protected dependencies remain required.'}
    return contours, audit
