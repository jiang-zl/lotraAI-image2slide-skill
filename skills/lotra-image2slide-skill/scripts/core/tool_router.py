"""Capability routing: shared core, optional platform/host tools.

Discovery reads configuration/executables, not repeated GUI probes. Host tools
receive staged work orders; they never get an implicit wider edit grant.
"""
import os
import platform
import shutil
from pathlib import Path
from .common import identity, read_json, writer


def capabilities(configuration=None,project=None):
    project=Path(project).resolve() if project else None
    local=project/'.lotraAI-build/toolchain/runtime.json' if project else None
    configured = read_json(local) if local and local.is_file() else {}
    if configuration:configured.update(configuration if isinstance(configuration,dict) else read_json(configuration))
    portable=project/'.lotraAI-build/Portable-renderer.json' if project else None
    if portable and portable.is_file():
        declared=read_json(portable).get('platforms',{}).get(platform.system(),{})
        if declared.get('executable'):configured.setdefault('soffice',declared['executable'])
    renderer = configured.get('soffice') or os.environ.get('LOTRAAI_SOFFICE')
    if not renderer:
        renderer = shutil.which('soffice')
    if not renderer:
        locations=[]
        if platform.system()=='Darwin':
            locations=[Path('/Applications/LibreOffice.app/Contents/MacOS/soffice'),Path.home()/'Applications/LibreOffice.app/Contents/MacOS/soffice']
        elif platform.system()=='Windows':
            locations=[Path(os.environ.get(key,'C:/Program Files'))/'LibreOffice/program/soffice.exe' for key in ('ProgramFiles','ProgramFiles(x86)')]
        renderer=next((str(path) for path in locations if path.is_file()),None)
    if renderer and not Path(renderer).is_file():
        renderer = None
    artifact = configured.get('artifact_tool', {})
    artifact_ready = bool(artifact.get('node') and Path(artifact['node']).is_file()
                          and artifact.get('module') and Path(artifact['module']).is_file())
    host = configured.get('host_tools', {})
    value = {'platform': platform.system(), 'project':str(project) if project else None,'configuration_mode':'explicit' if configuration else 'project',
             'native_pptx': {'available': True, 'kind': 'program'},
             'libreoffice': {'available': bool(renderer), 'executable': renderer,
                            'scope': 'configured_alternative_render'},
             'artifact_tool': {'available': artifact_ready, **artifact},
             'computer_use': {'available': bool(host.get('computer_use')), 'kind': 'host'},
             'image_generation': {'available': bool(host.get('image_generation')), 'kind': 'host'},
             'host_render': {'available': bool(host.get('host_render')), 'kind': 'host'},
             'host_tools': host}
    from .office_bridge import discover
    value['windows_office']=discover(configured.get('windows_office'))
    # Native Mac Office discovery is read-only. It does not assert that an
    # interactive host tool/permission is connected or install an application.
    mac_apps=[Path('/Applications/Microsoft PowerPoint.app'),Path.home()/'Applications/Microsoft PowerPoint.app'] if platform.system()=='Darwin' else []
    if configured.get('macos_office',{}).get('application'):
        mac_apps.insert(0,Path(configured['macos_office']['application']).expanduser())
    mac_info=next((p/'Contents/Info.plist' for p in mac_apps if (p/'Contents/Info.plist').is_file()),None)
    mac_metadata={}
    if mac_info:
        import plistlib
        with mac_info.open('rb') as file:mac_metadata=plistlib.load(file)
    value['macos_office']={'available':bool(mac_info),'application':str(mac_info.parent.parent) if mac_info else None,
                          'version':mac_metadata.get('CFBundleShortVersionString'),'build':mac_metadata.get('CFBundleVersion'),
                          'scope':'Installed application discovered; render/embed/edit still require an available configured or connected host tool'}
    value['resource_presence']={str(p/'Contents/Info.plist'):(p/'Contents/Info.plist').is_file() for p in mac_apps}
    value['render_preference']=configured.get('render_preference','auto')
    if project:
        from .presentation_backend import select
        value['presentation_backend']=select(project,configured.get('render_preference'),
            libreoffice=value['libreoffice'] if value['libreoffice']['available'] else None)
        value['saved_render_available']=value['presentation_backend'].get('status')=='READY'
        value['generator_profile']='office-safe-native-1.36.0'
        if not value['saved_render_available']:
            value['capability_error']=value['presentation_backend']
    fontconfig=configured.get('fontconfig')
    if fontconfig and Path(fontconfig).is_file():value['libreoffice']['fontconfig']=str(Path(fontconfig).resolve())
    elif project and platform.system()=='Linux':
        # Refer to fonts already installed on the WSL host, without installing
        # or redistributing them and without a desktop/API dependency.
        dirs=[Path(d).expanduser() for d in configured.get('font_dirs',[])[:16]]
        host_fonts=Path('/mnt/c/Windows/Fonts')
        if host_fonts.is_dir():dirs.append(host_fonts)
        dirs=list(dict.fromkeys(str(d.resolve()) for d in dirs if d.is_dir()))
        if dirs:
            from xml.sax.saxutils import escape
            root=project/'.lotraAI-build/toolchain';root.mkdir(parents=True,exist_ok=True)
            config=root/'host-fonts.conf';cache=root/'font-cache';cache.mkdir(exist_ok=True)
            xml='<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'+''.join('<dir>'+escape(d)+'</dir>' for d in dirs)+'<cachedir>'+escape(str(cache))+'</cachedir></fontconfig>'
            with writer(root):config.write_text(xml,encoding='utf-8')
            value['libreoffice'].update(fontconfig=str(config),host_font_dirs=dirs,font_scope='existing_host_fonts_process_private')
    if project:
        from .common import digest
        value['configuration_files']={str(project/name):digest(project/name) if (project/name).is_file() else None
            for name in ('.lotraAI-build/toolchain/runtime.json','.lotraAI-build/Portable-renderer.json','.lotraAI-build/Presentation-preferences.json')}
        from .font_resources import catalogue
        value['fonts'] = catalogue(project, value, configured)
        value['environment_cache'] = str(project/'.lotraAI-build/toolchain/environment.json')
    executables = [renderer, value.get('presentation_backend',{}).get('executable'),value['windows_office'].get('powerpoint'), value['windows_office'].get('powershell'),mac_info]
    value['executable_stamps'] = {str(p): [Path(p).stat().st_size, Path(p).stat().st_mtime_ns]
                                  for p in executables if p and Path(p).is_file()}
    value['fingerprint'] = identity(value)
    if project:
        from .common import write_json
        path = Path(value['environment_cache'])
        if not path.is_file() or read_json(path) != value:
            write_json(path, value)
    return value


def route(operation, policy, caps):
    if operation in ('text', 'math', 'shape', 'path', 'connector', 'native_parts', 'recipe'):
        helper = policy.get('executor', 'native_pptx')
        if helper == 'artifact_tool' and caps['artifact_tool']['available']:
            return {'executor': helper, 'scope': 'explicit_geometry_only', 'preserve_layout': True}
        return {'executor': 'native_pptx', 'scope': 'native_objects', 'preserve_layout': True}
    if operation == 'render':
        qualified=caps.get('presentation_backend')
        if qualified:
            if qualified.get('status')!='READY':return {'executor':None,'status':'CAPABILITY_BLOCKED','missing':qualified}
            if qualified.get('backend') in ('PowerPoint','WPS'):
                return {'executor':'qualified_native','capability':qualified,'scope':'actual_saved_file_program_export'}
            if qualified.get('backend')=='LibreOffice':
                return {'executor':'libreoffice','executable':qualified['executable']}
        office=caps.get('windows_office',{})
        preference=policy.get('renderer',caps.get('render_preference','powerpoint'))
        if preference=='powerpoint' and office.get('available'):
            return {'executor':'windows_office','scope':'actual_saved_file_program_export'}
        if policy.get('prefer_host') and caps['host_render']['available']:
            return {'executor': 'host_render', 'scope': 'actual_saved_file'}
        if caps['libreoffice']['available']:
            return {'executor': 'libreoffice', 'executable': caps['libreoffice']['executable']}
        if caps['host_render']['available']:
            return {'executor': 'host_render', 'scope': 'actual_saved_file'}
        return {'executor': None, 'status': 'CAPABILITY_LIMIT', 'missing': 'saved_pptx_render'}
    if operation in ('semantic_hd', 'amodal_completion'):
        if not policy.get('allow_raster'):
            return {'executor': 'native_pptx', 'scope': 'semantic_vector_redraw'}
        if caps['image_generation']['available']:
            return {'executor': 'image_generation', 'scope': 'specified_complete_semantic_layer'}
    if operation == 'desktop_edit' and caps['computer_use']['available']:
        return {'executor': 'computer_use', 'scope': 'staged_task_copy'}
    return {'executor': None, 'status': 'CAPABILITY_LIMIT', 'missing': operation}


def render_saved(pptx, out, caps, width):
    from .render import render
    chosen = route('render', {}, caps)
    if chosen['executor'] == 'qualified_native':
        from .presentation_backend import render as native_render
        try:return native_render(pptx,out,chosen['capability'],width=width)
        except (OSError,RuntimeError,ValueError) as error:
            # An explicit native request remains binding. Auto may use one
            # declared alternative, retaining the actual native failure.
            native=chosen['capability'];failure=Path(out)/'Backend-failure.json'
            if (native.get('selection',{}).get('requested')!='auto' or not caps.get('libreoffice',{}).get('available')
                    or not failure.is_file()):raise
            from .common import digest,write_json
            if read_json(failure).get('input_sha256')!=digest(pptx):raise ValueError('Unbound native failure cannot authorize fallback') from error
            import copy,uuid
            preserved=Path(out).with_name(Path(out).name+'-native-failed-'+uuid.uuid4().hex[:8])
            if preserved.exists() or Path(out).is_symlink():raise ValueError('Preserve unexpected native failure staging') from error
            Path(out).rename(preserved)
            fallback=copy.deepcopy(caps)
            fallback['presentation_backend']={'backend':'LibreOffice','status':'READY',**caps['libreoffice']}
            receipt=render_saved(pptx,out,fallback,width)
            receipt['native_export_failure']={'backend':native['backend'],'receipt':str(preserved/'Backend-failure.json'),
                'sha256':digest(preserved/'Backend-failure.json'),'policy':'one declared fallback after actual native PDF failure'}
            write_json(Path(out)/'render.json',receipt)
            return receipt
    if chosen['executor'] == 'windows_office':
        from .office_bridge import render as office_render
        return office_render(pptx,out,caps['windows_office'],width=width)
    if chosen['executor'] == 'libreoffice':
        if caps.get('presentation_backend') and caps.get('project'):
            from .portable_runtime import capabilities as portable_capabilities
            from .portable_editor import render as portable_render
            portable=portable_capabilities(caps['project'],requested='libreoffice')
            if portable.get('status')!='READY':raise ValueError(str(portable))
            return portable_render(pptx,out,portable,width=width)
        return render(pptx, out, width=width, executable=chosen['executable'],fontconfig=caps['libreoffice'].get('fontconfig'))
    raise RuntimeError('Host must supply an actual saved-file render: ' + str(chosen))


def environment_changed(caps, project):
    """Cheap cached-resource stamps, not repeated GUI/Office/font scans."""
    if caps.get('platform') != platform.system():
        return True
    if caps.get('configuration_files'):
        from .common import digest
        if any((digest(path) if Path(path).is_file() else None)!=sha for path,sha in caps['configuration_files'].items()):return True
    for path, stamp in caps.get('executable_stamps', {}).items():
        file = Path(path)
        if not file.is_file() or [file.stat().st_size, file.stat().st_mtime_ns] != stamp:
            return True
    if any(Path(path).is_file()!=exists for path,exists in caps.get('resource_presence',{}).items()):
        return True
    descriptor = caps.get('fonts', {})
    if not descriptor:
        return True
    catalogue_file = Path(descriptor['catalogue'])
    if not catalogue_file.is_file():
        return True
    record = read_json(catalogue_file)
    if record.get('environment_key')!=descriptor.get('environment_key'):
        return True  # Legacy shared catalogue was replaced by another route.
    if descriptor.get('catalogue_sha256'):
        from .common import digest
        if digest(catalogue_file)!=descriptor['catalogue_sha256']:return True
    for path, row in record.get('files', {}).items():
        file = Path(path)
        if not file.is_file():
            return True
        stat = file.stat()
        if [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns] != row['stamp']:
            return True
    local = Path(project)/'.lotraAI-build/toolchain/runtime.json'
    configuration = read_json(local) if local.is_file() else {}
    for path,stamp in record.get('directories',{}).items():
        directory=Path(path)
        if not directory.is_dir() or directory.stat().st_mtime_ns!=stamp:return True
    from .font_resources import roots
    if roots(caps,descriptor.get('font_config',{}))!=descriptor.get('discovery_roots',[]):return True
    return not caps.get('configuration_files') and caps.get('configuration_mode')!='explicit' and configuration != descriptor.get('font_config', {})
