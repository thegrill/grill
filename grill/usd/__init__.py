"""Helpers for USD workflows which do not know anything about the pipeline."""
import enum
# https://docs.python.org/3/whatsnew/3.10.html#pep-604-new-type-union-operator
# TODO: Remove when py-3.10+ is supported (for union types)
import typing
import inspect
import logging
import functools
import contextlib

import numpy as np

from itertools import chain
from collections import abc

from pxr import Usd, UsdGeom, Sdf, Plug, Ar, Tf
from printree import TreePrinter

logger = logging.getLogger(__name__)


@functools.cache
def _attr_value_type_names():
    values = inspect.getmembers(Sdf.ValueTypeNames, lambda v: isinstance(v, Sdf.ValueTypeName) and not v.isArray)
    return frozenset(chain.from_iterable(obj.aliasesAsStrings for name, obj in values))


@functools.cache
def _metadata_keys():
    # https://github.com/PixarAnimationStudios/USD/blob/7a5f8c4311fed3ef2271d5e4b51025fb0f513730/pxr/usd/sdf/textFileFormat.yy#L1400-L1409
    keys = {"doc", "subLayers"}
    keys.update(chain.from_iterable(p.metadata.get('SdfMetadata', {}) for p in Plug.Registry().GetAllPlugins()))

    # TODO: investigate if there's another way of doing this, like via the registry above
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Scope.Define(stage, "/a").MakeInvisible()

    layer = stage.GetRootLayer()
    layer.Traverse(layer.pseudoRoot.path, lambda path: keys.update(layer.GetObjectAtPath(path).GetMetaDataInfoKeys()))
    return frozenset(keys)


def _pruned_prims(prim_range: Usd.PrimRange, predicate):
    """Convenience generator that prunes a prim range based on the given predicate"""
    for prim in prim_range:
        if predicate(prim):
            prim_range.PruneChildren()
        yield prim


def common_paths(paths: abc.Iterable[Sdf.Path]) -> list[Sdf.Path]:
    """For the given :ref:`paths <glossary:path>`, get those which are the common parents."""
    unique = list()
    for path in sorted(filter(lambda p: p and not p.IsAbsoluteRootPath(), paths)):
        if unique and path.HasPrefix(unique[-1]):  # we're a child, so safe to continue.
            continue
        unique.append(path)
    return unique


def iprims(stage: Usd.Stage, root_paths: abc.Iterable[Sdf.Path] = tuple(), prune_predicate: abc.Callable[[Usd.Prim], bool] = None, traverse_predicate: typing.Union[Usd._Term, Usd._PrimFlagsConjunction] = Usd.PrimDefaultPredicate) -> abc.Iterator[Usd.Prim]:
    """Convenience function that creates an iterator useful for common :ref:`glossary:stage traversal`.

    Without keyword arguments, this is the same as calling :usdcpp:`UsdStage::Traverse`, so
    use that instead when neither ``root_paths`` nor ``prune_predicate`` are provided.

    A :usdcpp:`PrimRage <UsdPrimRange>` with the provided ``traverse_predicate`` is created for each :func:`common <common_paths>` :usdcpp:`Path <SdfPath>` in ``root_paths``,
    and :usdcpp:`PruneChildren <UsdPrimRange::iterator::PruneChildren>` is called whenever ``prune_predicate`` returns ``True`` for a traversed :usdcpp:`Prim <UsdPrim>`.

    """
    if root_paths:  # Traverse only specific parts of the stage.
        root_paths = common_paths(root_paths)
        # Usd.PrimRange already discards invalid prims, so no need to check.
        root_prims = map(stage.GetPrimAtPath, root_paths)
        ranges = (Usd.PrimRange(prim, traverse_predicate) for prim in root_prims)
    else:
        ranges = [Usd.PrimRange.Stage(stage, traverse_predicate)]

    return chain.from_iterable(
        (_pruned_prims(iter(r), prune_predicate) for r in ranges) if prune_predicate else ranges
    )


@functools.singledispatch
def edit_context(prim: Usd.Prim, /, query_filter: Usd.PrimCompositionQuery.Filter, predicate: abc.Callable[[Usd.CompositionArc], bool]) -> Usd.EditContext:
    """Get an :ref:`glossary:edittarget` for the first :usdcpp:`arc <UsdPrimCompositionQueryArc>` in the :ref:`Prims <glossary:prim>`'s :usdcpp:`composition <UsdPrimCompositionQuery>` for which the given ``predicate`` returns ``True``.

    Overloaded implementations allow for a direct search targetting :ref:`glossary:payload`, :ref:`glossary:references`, :ref:`glossary:specializes`, :ref:`glossary:inherits` and :ref:`glossary:variantset`.

    This allows for "chained" context switching while preserving the same stage objects.

    .. tip::

        You can try the below code snippet on ``USDView`` (or any other USD DCC application)
        Just swap the ``main = Usd.Stage.CreateInMemory()`` assignment for a stage on the viewport, e.g, for ``USDView``:

        .. code-block::  python

            >>> main = usdviewApi.stage

        Then paste the rest of the code as-is:

        .. image:: https://user-images.githubusercontent.com/8294116/133999486-b13e811a-91f4-4d8c-92d9-44c1f81b82d4.gif

    Example:
        >>> from pxr import Usd, UsdGeom, Sdf
        >>> main = Usd.Stage.CreateInMemory()
        >>> # Jump between 3 different layer stacks adding variants to the same set
        >>> # main [variant blue] -> reference [variant green] -> payload [variant red]
        >>> referenced = Usd.Stage.CreateInMemory()
        >>> referenced.SetDefaultPrim(referenced.DefinePrim("/Referenced"))
        >>> reference = Sdf.Reference(referenced.GetRootLayer().identifier)
        >>>
        >>> payloaded = Usd.Stage.CreateInMemory()
        >>> payloaded.SetDefaultPrim(payloaded.DefinePrim("/Payloaded"))
        >>> payload = Sdf.Payload(payloaded.GetRootLayer().identifier)
        >>>
        >>> top = main.DefinePrim("/Top")
        >>> top.GetReferences().AddReference(reference)
        True
        >>> import grill.usd as gusd
        >>> with gusd.edit_context(reference, top):
        ...     top.GetPayloads().AddPayload(payload)
        ...     with gusd.edit_context(payload, top):
        ...         geom = UsdGeom.Sphere.Define(main, top.GetPath().AppendPath("inner/child"))
        ...         color = geom.GetDisplayColorAttr()
        ...         color_set = geom.GetPrim().GetVariantSets().AddVariantSet("color")
        ...         color_set.AddVariant("from_payload")
        ...         color_set.SetVariantSelection("from_payload")
        ...         with gusd.edit_context(color_set, payloaded.GetRootLayer()):  # color_set.GetVariantEditContext() would fail here
        ...             color.Set([(1,0,0)])
        ...         color_set.ClearVariantSelection()
        ...     color_set.AddVariant("from_reference")
        ...     color_set.SetVariantSelection("from_reference")
        ...     with gusd.edit_context(color_set, referenced.GetRootLayer()):
        ...         color.Set([(0,1,0)])
        ...     color_set.ClearVariantSelection()
        ...
        True
        >>> color_set.AddVariant("from_top")
        >>> color_set.SetVariantSelection("from_top")
        >>> with color_set.GetVariantEditContext():
        ...     color.Set([(0,0,1)])
        ...
        >>> color_set.ClearVariantSelection()
        True
        >>> for each in main, referenced, payloaded:
        ...     print(each.GetRootLayer().ExportToString())
        ...
        #usda 1.0
        def "Top" (
            prepend references = @anon:0000019B6BE92A70:tmp.usda@
        )
        {
            over "inner"
            {
                over "child" (
                    prepend variantSets = "color"
                )
                {
                    variantSet "color" = {
                        "from_top" {
                            color3f[] primvars:displayColor = [(0, 0, 1)]
                        }
                    }
                }
            }
        }
        #usda 1.0
        (
            defaultPrim = "Referenced"
        )
        def "Referenced" (
            prepend payload = @anon:0000019B6BE93270:tmp.usda@
        )
        {
            over "inner"
            {
                over "child" (
                    prepend variantSets = "color"
                )
                {
                    variantSet "color" = {
                        "from_reference" {
                            color3f[] primvars:displayColor = [(0, 1, 0)]
                        }
                    }
                }
            }
        }
        #usda 1.0
        (
            defaultPrim = "Payloaded"
        )
        def "Payloaded"
        {
            def "inner"
            {
                def Sphere "child" (
                    prepend variantSets = "color"
                )
                {
                    variantSet "color" = {
                        "from_payload" {
                            color3f[] primvars:displayColor = [(1, 0, 0)]
                        }
                    }
                }
            }
        }

    """
    # https://blogs.mathworks.com/developer/2015/03/31/dont-get-in-too-deep/
    # with write.context(prim, dict(kingdom="assets")):
    #     prim.GetAttribute("abc").Set(True)
    # with write.context(stage, dict(kingdom="category")):
    #     stage.DefinePrim("/hi")
    query = Usd.PrimCompositionQuery(prim)
    query.filter = query_filter
    for arc in query.GetCompositionArcs():
        if predicate(arc):
            node = arc.GetTargetNode()
            target = Usd.EditTarget(node.layerStack.identifier.rootLayer, node)
            return Usd.EditContext(prim.GetStage(), target)
    raise ValueError(f"Could not find appropriate node for edit target for {prim} matching {predicate}")


@edit_context.register(Sdf.Reference)
@edit_context.register(Sdf.Payload)
def _(arc, /, prim: Usd.Prim) -> Usd.EditContext:
    identifier = arc.assetPath
    with Ar.ResolverContextBinder(prim.GetStage().GetPathResolverContext()):
        # Use Layer.Find since layer should have been open for the prim to exist.
        layer = Sdf.Layer.Find(identifier)
    if not layer:
        # Fallback to try find the layer directly. This might have been the result of an in memory stage.
        logger.debug(f"Layer with {identifier=} was not found on the resolver context for {prim=} at {prim.GetStage()}. Trying to find the layer outside of its context.")
        layer = Sdf.Layer.Find(identifier)
    if not layer:
        raise ValueError(f"Can't proceed without ability to find layer with {identifier=}")
    if not (arc.primPath or layer.defaultPrim):
        raise ValueError(f"Can't proceed without a prim path to target on arc {arc} for {layer}")
    path = arc.primPath or layer.GetPrimAtPath(layer.defaultPrim).path
    logger.debug(f"Searching to target {layer} on {path}")
    return _edit_context_by_arc(prim, type(arc), path, layer)


@edit_context.register(Usd.Specializes)
@edit_context.register(Usd.Inherits)
def _(arc, /, path: Sdf.Path, layer: Sdf.Layer) -> Usd.EditContext:
    return _edit_context_by_arc(arc.GetPrim(), type(arc), path, layer)


@edit_context.register(Usd.VariantSet)
def _(variant_set, /, layer: Sdf.Layer) -> Usd.EditContext:
    with contextlib.suppress(Tf.ErrorException):
        return variant_set.GetVariantEditContext()
    # ----- From Pixar -----
    # pxr.Tf.ErrorException:
    # 	Error in '...::UsdVariantSet::GetVariantEditTarget' ...: 'Layer <identifier> is not a local layer of stage rooted at layer <identifier>'
    # https://graphics.pixar.com/usd/docs/api/class_usd_variant_set.html#a83f3adf614736a0b43fa1dd5271a9528
    # Currently, we require layer to be in the stage's local LayerStack (see UsdStage::HasLocalLayer()), and will issue an error and return an invalid EditTarget if layer is not.
    # We may relax this restriction in the future, if need arises, but it introduces several complications in specification and behavior.
    # ---------------------
    prim = variant_set.GetPrim()
    name = variant_set.GetName()
    selection = variant_set.GetVariantSelection()
    logger.debug(f"Searching target for {prim} with variant {name}, {selection} on {layer}")

    def is_target(arc):
        node = arc.GetTargetNode()
        return node.path.GetVariantSelection() == (name, selection) and layer == node.layerStack.identifier.rootLayer

    query_filter = Usd.PrimCompositionQuery.Filter()
    query_filter.arcTypeFilter = Usd.PrimCompositionQuery.ArcTypeFilter.Variant
    query_filter.hasSpecsFilter = Usd.PrimCompositionQuery.HasSpecsFilter.HasSpecs
    return edit_context(prim, query_filter, is_target)


def _edit_context_by_arc(prim, arc_type, path, layer):
    arc_filter = {
        Sdf.Payload: Usd.PrimCompositionQuery.ArcTypeFilter.Payload,
        Sdf.Reference: Usd.PrimCompositionQuery.ArcTypeFilter.Reference,
        Usd.Inherits: Usd.PrimCompositionQuery.ArcTypeFilter.Inherit,
        Usd.Specializes: Usd.PrimCompositionQuery.ArcTypeFilter.Specialize,
    }
    query_filter = Usd.PrimCompositionQuery.Filter()
    query_filter.arcTypeFilter = arc_filter[arc_type]

    def is_target(arc):
        node = arc.GetTargetNode()
        # USD-23.02 can do arc.GetTargetPrimPath() == path and arc.GetTargetLayer() == layer
        return node.path == path and node.layerStack.identifier.rootLayer == layer

    return edit_context(prim, query_filter, is_target)


@contextlib.contextmanager
def _prim_tree_printer(predicate, prims_to_include: abc.Container = frozenset()):
    prim_entry = Usd.Prim.GetName if predicate != Usd.PrimIsModel else lambda prim: f"{prim.GetName()} ({Usd.ModelAPI(prim).GetKind()})"

    class PrimTreePrinter(TreePrinter):
        """For everything else, use usdtree from the vanilla USD toolset"""

        def ftree(self, prim: Usd.Prim):
            self.ROOT = f"{super().ROOT}{prim_entry(prim)}"
            return super().ftree(prim)

    # another duck
    Usd.Prim.__iter__ = lambda prim: (p for p in prim.GetFilteredChildren(predicate) if not prims_to_include or p in prims_to_include)
    Usd.Prim.items = lambda prim: ((prim_entry(p), p) for p in prim)
    current = type(abc.Mapping).__instancecheck__  # can't unregister abc.Mapping.register, so use __instancecheck__

    type(abc.Mapping).__instancecheck__ = lambda cls, inst: current(cls, inst) or (cls == abc.Mapping and type(inst) == Usd.Prim)
    try:
        yield PrimTreePrinter()
    finally:
        type(abc.Mapping).__instancecheck__ = current
        del Usd.Prim.__iter__
        del Usd.Prim.items


def _format_prim_hierarchy(prims, include_descendants=True, predicate=Usd.PrimDefaultPredicate):
    for prim in prims:
        if prim.IsPseudoRoot():
            prims_to_tree = {prim}
            break
    else:
        root_paths = dict.fromkeys(common_paths((prim.GetPath() for prim in prims)))
        prims_to_tree = (prim for prim in prims if prim.GetPath() in root_paths)

    with _prim_tree_printer(predicate, set(prims) if not include_descendants else set()) as printer:
        return "\n".join(printer.ftree(prim) for prim in prims_to_tree)


# add other mesh creation utilities here?
def _make_plane(mesh, width, depth):
    # https://github.com/marcomusy/vedo/issues/86
    # https://blender.stackexchange.com/questions/230534/fastest-way-to-skin-a-grid
    x_ = np.linspace(-(width / 2), width / 2, width)
    z_ = np.linspace(depth / 2, - depth / 2, depth)
    X, Z = np.meshgrid(x_, z_)
    x = X.ravel()
    z = Z.ravel()
    y = np.zeros_like(x)
    points = np.stack((x, y, z), axis=1)
    xmax = x_.size
    zmax = z_.size
    faceVertexIndices = np.array([
        (i + j * xmax, i + j * xmax + 1, i + 1 + (j + 1) * xmax, i + (j + 1) * xmax)
        for j in range(zmax - 1) for i in range(xmax - 1)
    ])

    faceVertexCounts = np.full(len(faceVertexIndices), 4)
    with Sdf.ChangeBlock():
        mesh.GetPointsAttr().Set(points)
        mesh.GetFaceVertexCountsAttr().Set(faceVertexCounts)
        mesh.GetFaceVertexIndicesAttr().Set(faceVertexIndices)


class _GeomPrimvarInfo(enum.Enum):  # TODO: find a better name
    # One element for the entire Imageable prim; no interpolation.
    CONSTANT = UsdGeom.Tokens.constant, {UsdGeom.Imageable: 1}
    # One element for each face of the mesh; elements are typically not interpolated
    # but are inherited by other faces derived from a given face (via subdivision, tessellation, etc.).
    UNIFORM = UsdGeom.Tokens.uniform, {
        UsdGeom.Mesh: lambda mesh: len(mesh.GetFaceVertexCountsAttr().Get()),
        UsdGeom.BasisCurves: lambda curve: curve.ComputeUniformDataSize(0),
        UsdGeom.Sphere: 100,  # TODO: there must be a better way of finding these numbers.
        UsdGeom.Cube: 6,
        UsdGeom.Capsule: 90,
        UsdGeom.Cone: 20,
        UsdGeom.Cylinder: 30,
    }
    # One element for each point of the mesh; interpolation of point data is:
    #   Varying: always linear.
    VARYING = UsdGeom.Tokens.varying, {
        UsdGeom.Mesh: lambda mesh: len(mesh.GetPointsAttr().Get()),
        UsdGeom.BasisCurves: lambda curve: curve.ComputeVaryingDataSize(0),
        UsdGeom.Sphere: 92,
        UsdGeom.Cube: 8,
        UsdGeom.Capsule: 82,
        UsdGeom.Cone: 31,
        UsdGeom.Cylinder: 42,
    }
    #   Vertex: applied according to the subdivisionScheme attribute.
    VERTEX = UsdGeom.Tokens.vertex, {**VARYING[1], UsdGeom.BasisCurves: lambda curve: curve.ComputeVertexDataSize(0)}
    # One element for each of the face-vertices that define the mesh topology;
    # interpolation of face-vertex data may be smooth or linear, according to the
    # subdivisionScheme and faceVaryingLinearInterpolation attributes.
    FACE_VARYING = UsdGeom.Tokens.faceVarying, {
        UsdGeom.Mesh: lambda mesh: len(mesh.GetFaceVertexIndicesAttr().Get()),
        UsdGeom.Sphere: 380,
        UsdGeom.Cube: 24,
        UsdGeom.Capsule: 340,
        UsdGeom.Cone: 70,
        UsdGeom.Cylinder: 100,
    }

    def size(self, prim):
        for geom_class, value in self.value[1].items():
            if geom := geom_class(prim):
                return value(geom) if callable(value) else value
        raise TypeError(f"Don't know how to compute '{self.interpolation()}' size on {self} for prim type '{prim.GetPrim().GetTypeName()}': {prim}")

    def interpolation(self):
        return self.value[0]
