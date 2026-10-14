"""Whole semantic-role coverage independent of constructor success receipts."""
from .common import identity

def evaluate(assemblies,source,native,candidate,pairs,execution=None):
    rows=[];known_pairs={r['id']:r for r in pairs}
    for assembly in assemblies:
        errors=[];roles=assembly.get('required_roles',[]);providers=assembly.get('providers',{})
        root=assembly.get('root')
        derived={r for r,value in source.items() if r==root or root in value.get('ancestors',[])} if root in source else set()
        if not derived or set(roles)!=derived:errors.append({'code':'ASSEMBLY_EXPECTED_ROLE_SET_INCOMPLETE','missing':sorted(derived-set(roles)),'root':root})
        if not roles or len(set(roles))!=len(roles):errors.append({'code':'ASSEMBLY_REQUIRED_ROLES_INVALID'})
        if set(roles)!=set(providers):errors.append({'code':'ASSEMBLY_PROVIDER_COVERAGE_INCOMPLETE','missing':sorted(set(roles)-set(providers))})
        for role in roles:
            provider=providers.get(role,{})
            if role not in source:errors.append({'code':'ASSEMBLY_SOURCE_ROLE_MISSING','role':role});continue
            names=source[role]['objects']
            if any(n not in native or native[n].get('nonpaint') for n in names):errors.append({'code':'ASSEMBLY_NATIVE_ROLE_MISSING','role':role})
            if provider.get('scope') not in ('part','assembly','inherited') or not provider.get('source_evidence') or role not in provider.get('covered_roles',[]):errors.append({'code':'ASSEMBLY_CONSTRUCTOR_SCOPE_INSUFFICIENT','role':role})
            current=provider if execution is None else execution.get(assembly['id'],{}).get(role,{})
            if current.get('execution_pptx_hash')!=candidate['pptx']['sha256'] or provider.get('objects')!=names or current.get('objects')!=names:
                errors.append({'code':'ASSEMBLY_PROVIDER_EXECUTION_STALE','role':role})
            measured=identity({n:{'geometry':native[n]['geometry'].wkt,'order':native[n]['order'],'method':native[n]['method']} for n in names if n in native and not native[n].get('nonpaint')})
            if current.get('native_dependency_hash')!=measured:errors.append({'code':'ASSEMBLY_PROVIDER_DEPENDENCY_CHANGED','role':role})
        # Related external roles also belong to the assembly's check closure.
        required=set(assembly.get('required_pair_ids',[]))|{r['id'] for r in pairs if set(r['objects'])&set(roles)}
        for rid in required:
            if rid not in known_pairs:errors.append({'code':'ASSEMBLY_RELATION_UNCHECKED','pair':rid})
            elif not known_pairs[rid]['passed']:errors.append({'code':'ASSEMBLY_RELATION_FAILED','pair':rid})
        rows.append({'id':assembly['id'],'passed':not errors,'errors':errors,'current_native_hash':candidate['pptx']['sha256'],
                     'role_dependency_hash':identity({r:source[r]['objects'] for r in roles if r in source}),
                     'scope':'Every expected role is implemented and independently measured now; a partial constructor receipt cannot close the whole assembly.'})
    return {'passed':all(r['passed'] for r in rows),'items':rows}
