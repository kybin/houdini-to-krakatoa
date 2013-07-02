import math
import os
import subprocess
import hou

def render(node):

    prescript = '''
import KrakatoaSR
import random
ri = KrakatoaSR.Ri()
'''
    option = optionScript(node)

    framebegin = 'ri.FrameBegin({0})\n'.format(int(hou.frame()))

    cam = hou.node(node.parm('camera').eval())

    outpath = node.parm('vm_picture').eval()
    display = 'ri.Display( "{outpath}", "file", "rgba" )'.format(outpath=outpath)
    print(display)

    resx,resy = cam.parmTuple('res').eval()
    aspect = cam.parm('aspect').eval()
    format = "ri.Format( {x}, {y}, {aspect} )".format(x=resx, y=resy, aspect=aspect)
    print(format)


    aperture = cam.parm('aperture').eval()
    aperture = min(aperture, aperture/resx*resy) # krakatoa uses renderman style
    focal = cam.parm('focal').eval()

    fov = math.degrees(2*math.atan(aperture/2/focal))
    camtrans = cam.worldTransform().inverted()*hou.Matrix4([[1,0,0,0],[0,1,0,0],[0,0,-1,0],[0,0,0,1]])
    camtrans = [str(i) for i in camtrans.asTuple()]
    cam_projection = 'ri.Projection( "perspective", "fov", {fov} )'.format(fov=fov)
    cam_transform = 'ri.Transform({transmatrix})'.format(transmatrix=','.join(camtrans))

    worldbegin = '\nri.WorldBegin()'

    #Surface!
    # In houdini : object.worldTransform()

    prtfile = node.parm('scene_prt').evalAsString()
    objectscript = '''ri.AttributeBegin()
ri.Surface( "Isotropic" )
ri.Transform(1,0,0,0,  0,1,0,0,  0,0,1,0,  0,0,0,1)
ri.PointsFile("{0}")
ri.AttributeEnd()

'''.format(prtfile)
    
    worldend = 'ri.WorldEnd()'
    frameend = 'ri.FrameEnd()'

    ss = [] #scene script
    ss.append(prescript)
    ss.append(option)
    ss.append(framebegin)
    ss.append(display)
    ss.append(format)
    ss.append(cam_projection)
    ss.append(cam_transform)
    ss.append(worldbegin)
    ss.append(lightScript(node))
    ss.append(objectscript)
    ss.append(worldend)
    ss.append(frameend)
    
    # make prt
    try:
        tmpobj = hou.node('/obj/tmp_krakatoa')
        tmpsop = tmpgeo.node('krakatoa_export')
    except:
        tmpobj = hou.node('/obj').createNode('geo')
        tmpobj.setName('tmp_krakatoa')
        tmpsop = tmpobj.createNode('object_merge')
        tmpsop.setName('krakatoa_export')

    ksops = hou.node('/obj').glob('krakatoa*')
    ksops = [i for i in ksops if i.isDisplayFlagSet()]
    tmpsop.parm('numobj').set(len(ksops))
    for i, s in enumerate(ksops):
        parmname = 'objpath'+str(i+1)
        tmpsop.parm(parmname).set(s.path())
    tmpgeo = tmpsop.geometry()
    tmpgeo.saveToFile(prtfile)
    tmpobj.destroy() # for debug turn this off

    # make scene description
    scenefile = node.parm('scene_description').evalAsString()
    with open(scenefile, 'w') as f:
        f.write('\n'.join(ss))
    output,error = subprocess.Popen(['python', scenefile],stdout = subprocess.PIPE, stderr= subprocess.PIPE).communicate()
    print(error)


def optionScript(node):
    density = node.parm('DensityPerParticle').eval()
    ldensity = node.parm('LightingDensityPerParticle').eval()

    options= []

    if node.parm("RenderingMethod").evalAsString()=="voxel":
        options.append('''
ri.Option( "render", "RenderingMethod", "voxel")
ri.Option( "render", "VoxelSize", {0})
ri.Option( "render", "VoxelFilterRadius", {1} )'''.format(node.parm("VoxelSize").eval(), node.parm("VoxelFilterRadius").eval()))

    options.append('ri.Option( "render", "DensityPerParticle", {0}, "DensityExponent", -5 )'.format(density))
    options.append('ri.Option( "render", "LightingDensityPerParticle", {0}, "LightingDensityExponent", -5)'.format(ldensity))
    options.append('ri.Option( "render", "AttenuationLookupFilter", "{0}" )'.format(node.parm("AttenuationLookupFilter").evalAsString()))
    options.append('ri.Option( "render", "DrawPointFilter", "{0}" )'.format(node.parm("DrawPointFilter").evalAsString()))
    options.append('ri.Option( "channels", "DefaultColor", {0} )'.format(node.parmTuple('DefaultColor').evalAsFloats()))
    if node.parm('CheckOverrideColor').eval():
        options.append('ri.Option( "channels", "OverrideColor", {0} )'.format(node.parmTuple('OverrideColor').evalAsFloats()))
    if node.parm('CheckOverrideEmissionColor').eval():
        options.append('ri.Option( "channels", "OverrideEmissionColor", {0} )'.format(node.parmTuple('OverrideEmissionColor').evalAsFloats()))
    if node.parm('CheckOverrideAbsorptionColor').eval():
        options.append('ri.Option( "channels", "OverrideAbsorptionColor", {0} )'.format(node.parmTuple('OverrideAbsorptionColor').evalAsFloats()))

    return '\n'.join(options)

def lightScript(node):
    lights = hou.node('/obj').recursiveGlob('*', filter=hou.nodeTypeFilter.ObjLight)
    lights = [l for l in lights if l.parm('light_enable').eval()]
    script=''

    for l in lights:
        name = l.name()
        transform = l.worldTransform().asTuple()
        color = l.parmTuple('light_color').eval()
        intensity = l.parm('light_intensity').eval()
        flux = tuple([c*intensity for c in color])

        defaultlight = 'spotlight'
        if l.parm('light_type') == 'point' and l.parm('coneenable'):
            ltype = 'spotlight'
        elif l.parm('light_type') == 'point' and not l.parm('coneenable'):
            ltype = 'pointlight'
        elif l.parm('light_type') == 'distant':
            ltype = 'directlight'
        else:
            ltype = defaultlight

        script += '''
ri.AttributeBegin()
ri.Transform( {transform} )
ri.LightSource( "{ltype}", "{name}",
    "Flux", {flux},
    "DecayExponent", 0,
    "ShadowsEnabled", True,
    "ShadowDensity", 1.0,
    "ShadowMapWidth", 1024,
    "UseNearAttenuation", False,
    "UseFarAttenuation", False,
    "NearAttenuationStart", 0.0,
    "NearAttenuationEnd", 40.0,
    "FarAttenuationStart", 80.0,
    "FarAttenuationEnd", 200.0,
    "LightShape", "round", ##can also be "square"
    "LightAspect", 1.0,
    "InnerRadius", 10,
    "OuterRadius", 11 )
ri.AttributeEnd()
ri.Illuminate( "{name}", True )
'''.format(transform=transform, ltype=ltype, name=name, flux=flux)

    return script

def PRTmultiplicationScript(node):
    radius = node.parm('ParticleRadius').eval()
    spacing = node.parm('VoxelSpacing').eval()
    subdiv = node.parm('VoxelSubdivisions')

    script = '''ri.AttributeBegin()
ri.Surface( "Isotropic" )
ri.Option( "pointsvolume", "ParticleRadius", {radius} )
ri.Option( "pointsvolume", "VoxelSpacing", {spacing} )
ri.Option( "pointsvolume", "VoxelSubdivisions", {subdiv} )'''.format(radius=radius, spacing=spacing, subdiv=subdiv)
    if node.parm('Jitter').eval():
        ppvoxel = node.parm('JitteredParticlesPerVoxel').eval()
        seed = node.parm('RandomSeed').eval()
        randval = node.parm('NumDistinctRandomValues')
        distribute = node.parm('WellDistributedJittering')
        script += '''
ri.Option( "pointsvolume", "Jitter", True )
ri.Option( "pointsvolume", "JitteredParticlesPerVoxel", {ppvoxel} )
ri.Option( "pointsvolume", "RandomSeed", {seed} )
ri.Option( "pointsvolume", "NumDistinctRandomValues", {randval} )
ri.Option( "pointsvolume", "WellDistributedJittering", {distribute} )'''.format(ppvoxel=ppvoxel, seed=seed, randval=randval, distribute=distribute)
    
    script +='''
ri.PointsVolume( "{0}" )
ri.AttributeEnd()'''.format(node.parm('scene_prt').eval())

    return script