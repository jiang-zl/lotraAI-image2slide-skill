"""Original graph suggestions; native two-terminal connectors never branch."""
from .common import identity
from .line_contracts import segment_ends


def prepare(observation):
    features={f['id']:f for f in observation['features'] if f.get('line')};edges=[];junctions={};routes=[]
    for feature in features.values():
        line=feature['line'];ids=[]
        for index,segment in enumerate(line['path']['segments']):
            first,last=segment_ends(segment);name=feature['id']+':'+str(index);ids.append(name)
            edges.append({'id':name,'feature':feature['id'],'segment':index,'from':first,'to':last,
                          'source_segment_hash':identity(segment),'shared_with':[]})
        for kind in ('junctions','crossings','shared'):
            for item in line['topology'][kind]:
                key=kind+':'+item['id']
                if key in junctions and junctions[key]['source_record']!=item:
                    raise ValueError('BRANCH_SOURCE_DECISION_REQUIRED: reciprocal topology records disagree')
                junctions[key]={'kind':kind,'source_record':item}
        count=len(line['path']['segments'])
        routes.append({'feature':feature['id'],'required_edges':ids,'terminals':len(line['ends']),
            'suggested_native':'native_connector' if count==1 and line['path']['kind']=='straight' else 'ordered_native_path',
            'rule':'One contiguous two-terminal source route per path. Split a bus and its branches into explicitly bound owners; bentConnector2/3 cannot add a third terminal.'})
    # Reuse is only suggested for a source-declared shared edge with identical
    # route and stroke; a geometric crossing does not authorize deduplication.
    for record in junctions.values():
        if record['kind']!='shared':continue
        peers=record['source_record']['features']
        for edge in edges:
            if edge['feature'] not in peers:continue
            for other in edges:
                if other['feature']==edge['feature'] or other['feature'] not in peers:continue
                if ((edge['from']==other['from'] and edge['to']==other['to']) or
                    (edge['from']==other['to'] and edge['to']==other['from'])) and features[edge['feature']]['line']['stroke']==features[other['feature']]['line']['stroke']:
                    edge['shared_with'].append(other['id'])
    return {'schema':'source-branch-plan-1.37.5','source_hash':observation['source_hash'],
            'source_observation_hash':identity(observation),'edges':edges,'topology':list(junctions.values()),'routes':routes,
            'coverage':{'source_edges':len(edges),'planned_edge_ids':sorted(e['id'] for e in edges)},
            'automatic_native_write':False,'alignment_or_snapping':False,
            'acceptance':'Source/native incidence, each short segment and actual render still require independent verification'}
