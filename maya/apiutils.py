# grill
from grill.maya.names import MyAttribute


def findPlug(target_dg_name, mplugs, depth=0, depth_limit=5, found_plug=None):
    if depth>depth_limit:
        return
    depth+=1
    for mplug in mplugs:
        mdepnode, dg_name = _getMDependencyNodePath(mplug.node())
        if dg_name==target_dg_name:
            return mplug
        affected_plugs = {}
        for p in mdepnode.getAffectedAttributes(mplug.attribute()):
            mp = om.MPlug(mplug.node(), p)
            affected_plugs[mp.partialName(useLongNames=True)] = mp
        if len(affected_plugs)!=1:
            try:
                attribute = MyAttribute(mplug.partialName(useLongNames=True))
            except NameError: #not a valid or supported attribute
                continue
            plugs = affected_plugs[attribute.getName(plug='out', index='')].destinations()
        else:
            plugs = mp.destinations()
        return findPlug(target_dg_name, plugs, depth, depth_limit, found_plug)

def getMDependencyNodePath(mobject):
    mdepnode = om.MFnDagNode(mobject)
    try:
        node_dg_name = mdepnode.getPath().fullPathName()
    except RuntimeError:
        mdepnode = om.MFnDependencyNode(mobject)
        node_dg_name = mdepnode.name()
    return mdepnode, node_dg_name
