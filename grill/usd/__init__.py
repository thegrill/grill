"""Helpers for USD workflows which do not know anything about the grill pipeline."""
import itertools

from pxr import Usd


def _pruned_prims(prim_range: Usd.PrimRange, predicate):
    """Convenience generator that prunes a prim range based on the given predicate"""
    for prim in prim_range:
        if predicate(prim):
            prim_range.PruneChildren()
        yield prim


def common_paths(paths):
    """For the given paths, get those which are the common parents."""
    unique = list()
    for path in sorted(filter(lambda p: p and not p.IsAbsoluteRootPath(), paths)):
        if unique and path.HasPrefix(unique[-1]):  # we're a child, so safe to continue.
            continue
        unique.append(path)
    return unique


def iprims(stage, root_paths=None, prune_predicate=None, traverse_predicate=Usd.PrimDefaultPredicate):
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
