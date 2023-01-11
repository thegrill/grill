"""Helpers for USD workflows which do not know anything about the pipeline."""
import enum
import typing
import inspect
import logging
import functools
import contextlib

from itertools import chain

from pxr import Usd, UsdGeom, Sdf, Plug, Ar, Tf

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


def common_paths(paths: typing.Iterable[Sdf.Path]) -> typing.List[Sdf.Path]:
    """For the given paths, get those which are the common parents."""
    unique = list()
    for path in sorted(filter(lambda p: p and not p.IsAbsoluteRootPath(), paths)):
        if unique and path.HasPrefix(unique[-1]):  # we're a child, so safe to continue.
            continue
        unique.append(path)
    return unique


def iprims(stage: Usd.Stage, root_paths: typing.Iterable[Sdf.Path] = tuple(), prune_predicate: typing.Callable = None, traverse_predicate=Usd.PrimDefaultPredicate) -> typing.Iterator[Usd.Prim]:
    """Convenience function that creates a generator useful for common prim traversals.

    Without keyword arguments, this is the same as calling `Usd.Stage.Traverse(...)`, so
    use that instead when no `root_paths` or `prune_predicates` are needed.
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


@typing.overload
def edit_context(payload: Sdf.Payload, /, prim: Usd.Prim) -> Usd.EditContext:
    ...


@typing.overload
def edit_context(reference: Sdf.Reference, /, prim: Usd.Prim) -> Usd.EditContext:
    ...


@typing.overload
def edit_context(variant: Usd.VariantSet, /, layer: Sdf.Layer) -> Usd.EditContext:
    ...


@typing.overload
def edit_context(prim: Usd.Prim, /, query_filter: Usd.PrimCompositionQuery.Filter, target_predicate: typing.Callable) -> Usd.EditContext:
    ...


@functools.singledispatch
def edit_context(obj, /, *args, **kwargs) -> Usd.EditContext:
    """Composition arcs target layer stacks. These functions help create EditTargets for the first matching node's root layer stack from prim's composition arcs.

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
    raise TypeError(f"Not implemented: {locals()}")  # lazy


@edit_context.register
def _(prim: Usd.Prim, /, query_filter, target_predicate):
    # https://blogs.mathworks.com/developer/2015/03/31/dont-get-in-too-deep/
    # with write.context(prim, dict(kingdom="assets")):
    #     prim.GetAttribute("abc").Set(True)
    # with write.context(stage, dict(kingdom="category")):
    #     stage.DefinePrim("/hi")
    query = Usd.PrimCompositionQuery(prim)
    query.filter = query_filter
    for arc in query.GetCompositionArcs():
        if target_predicate(node := arc.GetTargetNode()):
            target = Usd.EditTarget(node.layerStack.identifier.rootLayer, node)
            return Usd.EditContext(prim.GetStage(), target)
    raise ValueError(f"Could not find appropriate node for edit target for {prim} matching {target_predicate}")


@edit_context.register(Sdf.Reference)
@edit_context.register(Sdf.Payload)
def _(arc: typing.Union[Sdf.Payload, Sdf.Reference], /, prim):
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

    def is_valid_target(node):
        return node.path == path and node.layerStack.identifier.rootLayer == layer

    query_filter = Usd.PrimCompositionQuery.Filter()
    if isinstance(arc, Sdf.Payload):
        query_filter.arcTypeFilter = Usd.PrimCompositionQuery.ArcTypeFilter.Payload
    elif isinstance(arc, Sdf.Reference):
        query_filter.arcTypeFilter = Usd.PrimCompositionQuery.ArcTypeFilter.Reference

    query_filter.hasSpecsFilter = Usd.PrimCompositionQuery.HasSpecsFilter.HasSpecs
    return edit_context(prim, query_filter, is_valid_target)


@edit_context.register
def _(variant_set: Usd.VariantSet, /, layer):
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

    def is_valid_target(node):
        return node.path.GetVariantSelection() == (name, selection) and layer == node.layerStack.identifier.rootLayer

    query_filter = Usd.PrimCompositionQuery.Filter()
    query_filter.arcTypeFilter = Usd.PrimCompositionQuery.ArcTypeFilter.Variant
    query_filter.hasSpecsFilter = Usd.PrimCompositionQuery.HasSpecsFilter.HasSpecs
    return edit_context(prim, query_filter, is_valid_target)


class _GeomPrimvarInfo(enum.Enum):  # TODO: find a better name
    _ignore_ = 'sizes'
    # One element for the entire Gprim; no interpolation.
    CONSTANT = UsdGeom.Tokens.constant, {UsdGeom.Gprim: 1}
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
