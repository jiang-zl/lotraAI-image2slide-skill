"""Freeze source tolerances before searching; failed candidates are not inputs."""
from .component_protocol import finite


def source_tolerance(uncertainty, quantization, coefficients, source_evidence):
    finite([uncertainty,quantization,coefficients])
    if any(type(v) not in (float,int) for v in (uncertainty,quantization,*coefficients.values())):
        raise ValueError('Calibration inputs must be numeric, not boolean')
    if not source_evidence or min(uncertainty,quantization)<0:
        raise ValueError('Located original uncertainty and discretization required')
    a,b,low,high=[coefficients[key] for key in ('uncertainty_weight','quantization_weight','lower','upper')]
    if min(a,b,low)<0 or high<low: raise ValueError('Predeclared nonnegative calibration limits required')
    raw=a*uncertainty+b*quantization
    if raw>high:
        return {'status':'SOURCE_DECISION_REQUIRED','raw':raw,'upper':high,
                'reason':'Original uncertainty exceeds the calibrated permitted range'}
    return {'status':'FROZEN_SOURCE_TOLERANCE','value':max(low,raw),'raw':raw,
            'coefficients':coefficients,'source_evidence':source_evidence,
            'role':'target','statistical_confidence_claim':False}
