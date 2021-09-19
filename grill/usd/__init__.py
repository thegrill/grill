"""Helpers for USD workflows which do not know anything about the pipeline."""
import typing
import logging
import itertools
import functools
import contextlib

from pxr import Usd, Tf, Ar, Sdf

logger = logging.getLogger(__name__)


def _pruned_prims(prim_range: Usd.PrimRange, predicate):
    """Convenience generator that prunes a prim range based on the given predicate"""
    for prim in prim_range:
        if predicate(prim):
            prim_range.PruneChildren()
        yield prim


def common_paths(paths: typing.Iterable[Sdf.Path]) -> list[Sdf.Path]:
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

    return itertools.chain.from_iterable(
        (_pruned_prims(iter(r), prune_predicate) for r in ranges) if prune_predicate else ranges
    )


@typing.overload
def edit_context(variant: Usd.VariantSet, layer: Sdf.Layer) -> Usd.EditContext:
    ...


@typing.overload
def edit_context(payload: Sdf.Payload, prim: Usd.Prim) -> Usd.EditContext:
    ...


@typing.overload
def edit_context(prim: Usd.Prim, query_filter: Usd.PrimCompositionQuery.Filter, target_predicate: typing.Callable) -> Usd.EditContext:
    ...


@functools.singledispatch
def edit_context(obj, layer) -> Usd.EditContext:
    """Composition arcs target layer stacks.

    These overloaded functions help construct EditTargets for the first matching node's root layer stack.

    Examples:
        >>> from pxr import Usd, UsdGeom, Sdf
        >>> main = Usd.Stage.CreateInMemory()
        >>> a = main.DefinePrim("/a")
        >>> payloaded = Usd.Stage.CreateInMemory()
        >>> x = payloaded.DefinePrim("/x")
        >>> payload = Sdf.Payload(payloaded.GetRootLayer().identifier, x.GetPath())
        >>> a.GetPayloads().AddPayload(payload)
        True
        >>> import grill.usd as gusd
        >>> with gusd.edit_context(payload, a):
        ...     geom = UsdGeom.Sphere.Define(main, a.GetPath().AppendPath("inner/child"))
        ...
        >>> geom.GetPrim().GetStage() is main
        True
        >>> geom.GetPath()
        Sdf.Path('/a/inner/child')
        >>> print(main.GetRootLayer().ExportToString())
        #usda 1.0
        def "a" (
            prepend payload = @anon:0000029AB64DF6E0:tmp.usda@</x>
        )
        {
        }
        >>> print(payloaded.GetRootLayer().ExportToString())
        #usda 1.0
        def "x"
        {
            def "inner"
            {
                def Sphere "child"
                {
                }
            }
        }


    get an edit context from a query filter + a filter predicate, using the root layer
    of the matching target node as the edit target layer.
    """
    raise TypeError(f"Not implemented: {locals()}")  # lazy


@edit_context.register
def _(prim: Usd.Prim, query_filter, target_predicate):
    query = Usd.PrimCompositionQuery(prim)
    query.filter = query_filter
    for arc in query.GetCompositionArcs():
        node = arc.GetTargetNode()
        if target_predicate(node):
            target = Usd.EditTarget(node.layerStack.identifier.rootLayer, node)
            return Usd.EditContext(prim.GetStage(), target)
    raise ValueError(f"Could not find appropriate node for edit target for {prim} matching {target_predicate}")


@edit_context.register
def _(payload: Sdf.Payload, prim):
    with Ar.ResolverContextBinder(prim.GetStage().GetPathResolverContext()):
        # Use Layer.Find since layer should have been open for the prim to exist.
        layer = Sdf.Layer.Find(payload.assetPath)
    if not (payload.primPath or layer.defaultPrim):
        raise ValueError(f"Can't proceed without a prim path to target on payload {payload} for {layer}")
    path = payload.primPath or layer.GetPrimAtPath(layer.defaultPrim).path
    logger.debug(f"Searching to target {layer} on {path}")

    def is_valid_target(node):
        return node.path == path and node.layerStack.identifier.rootLayer == layer

    query_filter = Usd.PrimCompositionQuery.Filter()
    query_filter.arcTypeFilter = Usd.PrimCompositionQuery.ArcTypeFilter.Payload
    query_filter.hasSpecsFilter = Usd.PrimCompositionQuery.HasSpecsFilter.HasSpecs
    return edit_context(prim, query_filter, is_valid_target)


@edit_context.register
def _(variant_set: Usd.VariantSet, layer):
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
