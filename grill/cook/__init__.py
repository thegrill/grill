"""Inspecting, authoring and editing foundational tools for the pipeline.

.. data:: Repository

    :class:`contextvars.ContextVar` for the global asset repository location.

    It's value must always be set to a :class:`pathlib.Path`.

    .. attention::
        By default, no value has been set. Ensure to set it before performing any creation operation.

    Example:
        >>> Repository.get()  # not set
        Traceback (most recent call last):
          File "<input>", line 1, in <module>
        LookupError: <ContextVar name='Repository' at 0x00000207F0A12B88>
        >>> import tempfile
        >>> from pathlib import Path
        >>> Repository.set(Path(tempfile.mkdtemp()))
        <Token var=<ContextVar name='Repository' at 0x00000213A46FF900> at 0x00000213C6A9F0C0>
        >>> Repository.get()
        WindowsPath('C:/Users/CHRIST~1/AppData/Local/Temp/tmp767wqaya')

"""

from __future__ import annotations

import types
import typing
import logging
import functools
import itertools
import contextlib
import contextvars
from pathlib import Path
from pprint import pformat

from pxr import UsdUtils, UsdGeom, Usd, Sdf, Kind, Ar, Tf
from grill import usd as _usd, names as _names
from grill.tokens import ids

logger = logging.getLogger(__name__)

Repository = contextvars.ContextVar('Repository')

_TAXA_KEY = 'taxa'
_FIELDS_KEY = 'fields'
_ASSETINFO_KEY = 'grill'
_ASSETINFO_TAXA_KEY = f'{_ASSETINFO_KEY}:{_TAXA_KEY}'
_ASSETINFO_FIELDS_KEY = f'{_ASSETINFO_KEY}:{_FIELDS_KEY}'

# Taxonomy rank handles the grill classification and grouping of assets.
_TAXONOMY_NAME = 'Taxonomy'
_TAXONOMY_ROOT_PATH = Sdf.Path.absoluteRootPath.AppendChild(_TAXONOMY_NAME)
_TAXONOMY_UNIQUE_ID = ids.CGAsset.cluster  # High level organization of our assets.
_TAXONOMY_FIELDS = types.MappingProxyType({_TAXONOMY_UNIQUE_ID.name: _TAXONOMY_NAME})
_ASSETINFO_TAXON_KEY = f'{_ASSETINFO_FIELDS_KEY}:{_TAXONOMY_UNIQUE_ID.name}'

_CATALOGUE_NAME = 'Catalogue'
_CATALOGUE_ROOT_PATH = Sdf.Path.absoluteRootPath.AppendChild(_CATALOGUE_NAME)
_CATALOGUE_ID = ids.CGAsset.kingdom  # where all existing units will be "discoverable"
_CATALOGUE_FIELDS = types.MappingProxyType({_CATALOGUE_ID.name: _CATALOGUE_NAME})

_UNIT_UNIQUE_ID = ids.CGAsset.item  # Entry point for meaningful composed assets.
_UNIT_ORIGIN_PATH = Sdf.Path.absoluteRootPath.AppendChild("Origin")

# Composition filters for asset edits
_ASSET_UNIT_QUERY_FILTER = Usd.PrimCompositionQuery.Filter()
_ASSET_UNIT_QUERY_FILTER.dependencyTypeFilter = Usd.PrimCompositionQuery.DependencyTypeFilter.Direct
_ASSET_UNIT_QUERY_FILTER.hasSpecsFilter = Usd.PrimCompositionQuery.HasSpecsFilter.HasSpecs


@functools.lru_cache(maxsize=None)
def fetch_stage(identifier: str, resolver_ctx: Ar.ResolverContext = None) -> Usd.Stage:
    """Retrieve the `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_ whose root `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_ matches the given ``identifier``.

    If the `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_ does not exist, it is created in the repository.

    If an open matching `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_ is found on the `global cache <https://graphics.pixar.com/usd/docs/api/class_usd_utils_stage_cache.html>`_, return it.
    Otherwise open it, populate the `cache <https://graphics.pixar.com/usd/docs/api/class_usd_utils_stage_cache.html>`_ and return it.

    .. attention::
        ``identifier`` must be a valid :class:`grill.names.UsdAsset` name.

    """
    layer_id = _names.UsdAsset(identifier).name
    cache = UsdUtils.StageCache.Get()
    if not resolver_ctx:
        repo_path = Repository.get()
        resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])
    else:  # TODO: see how to make this work, seems very experimental atm.
        repo_path = Path(resolver_ctx.Get()[0].GetSearchPath()[0])

    with Ar.ResolverContextBinder(resolver_ctx):
        logger.debug(f"Searching for {layer_id}")
        layer = Sdf.Layer.Find(layer_id)
        if not layer:
            logger.debug(f"Layer {layer_id} was not found open. Attempting to open it.")
            if not Sdf.Layer.FindOrOpen(layer_id):
                logger.debug(f"Layer {layer_id} does not exist on repository path: {repo_path}. Creating a new one.")
                # we first create a layer under our repo
                tmp_new_layer = Sdf.Layer.CreateNew(str(repo_path / layer_id))
                # delete it since it will have an identifier with the full path,
                # and we want to have the identifier relative to the repository path
                # TODO: with AR 2.0 it should be possible to create in memory layers
                #   with relative identifers to that of the search path of the context.
                #   In the meantime, we need to create the layer first on disk.
                del tmp_new_layer
            stage = Usd.Stage.Open(layer_id)
            logger.debug(f"Opened stage: {stage}")
            cache_id = cache.Insert(stage)
            logger.debug(f"Added stage for {layer_id} with cache ID: {cache_id.ToString()}.")
        else:
            logger.debug(f"Layer was open. Found: {layer}")
            stage = cache.FindOneMatching(layer)
            if not stage:
                logger.debug("Could not find stage on the cache.")
                stage = Usd.Stage.Open(layer)
                cache_id = cache.Insert(stage)
                logger.debug(f"Added stage for {layer} with cache ID: {cache_id.ToString()}.")
            else:
                logger.debug(f"Found stage: {stage}")

    return stage


def define_taxon(stage: Usd.Stage, name: str, *, references: tuple.Tuple[Usd.Prim] = tuple(), id_fields: typing.Mapping[str, str] = types.MappingProxyType({})) -> Usd.Prim:
    """Define a new `taxon group <https://en.wikipedia.org/wiki/Taxon>`_ for asset `taxonomy <https://en.wikipedia.org/wiki/Taxonomy>`_.

    If an existing ``taxon`` with the provided name already exists in the `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_, it is used.

    The new ``taxon`` can extend from existing ``taxa`` via the ``references`` argument.

    Optional ``field=value`` items can be provided for identification purposes via ``id_fields``.

    :returns: `Prim <https://graphics.pixar.com/usd/docs/api/class_usd_prim.html>`_ representing the ``taxon`` group.
    """
    if name == _TAXONOMY_NAME:
        # TODO: prevent upper case lower case mismatch handle between multiple OS?
        #  (e.g. Windows considers both the same but Linux does not)
        raise ValueError(f"Can not define a taxon with reserved name: '{_TAXONOMY_NAME}'.")

    reserved_fields = {_TAXONOMY_UNIQUE_ID, _UNIT_UNIQUE_ID}
    reserved_fields.update([i.name for i in reserved_fields])
    intersection = reserved_fields.intersection(id_fields)
    if intersection:
        raise ValueError(f"Can not provide reserved id fields: {', '.join(map(str, intersection))}. Got fields: {', '.join(map(str, id_fields))}")

    fields = {
        (token.name if isinstance(token, ids.CGAsset) else token): value
        for token, value in id_fields.items()
    }
    invalid_fields = set(fields).difference(ids.CGAsset.__members__)
    if invalid_fields:
        raise ValueError(f"Got invalid id_field keys: {', '.join(invalid_fields)}. Allowed: {', '.join(ids.CGAsset.__members__)}")

    with taxonomy_context(stage):
        prim = stage.DefinePrim(_TAXONOMY_ROOT_PATH.AppendChild(name))
        for reference in references:
            prim.GetReferences().AddInternalReference(reference.GetPath())
        prim.CreateAttribute("label", Sdf.ValueTypeNames.String, custom=False)
        taxon_fields = {**fields, _TAXONOMY_UNIQUE_ID.name: name}
        prim.SetAssetInfoByKey(_ASSETINFO_KEY, {_FIELDS_KEY: taxon_fields, _TAXA_KEY: {name: 0}})

    return prim


def itaxa(prims, taxon, *taxa):
    """Yields prims that are part of the given taxa."""
    taxa_names = {i if isinstance(i, str) else i.GetName() for i in (taxon, *taxa)}
    return (prim for prim in prims if taxa_names.intersection(prim.GetAssetInfoByKey(_ASSETINFO_TAXA_KEY) or {}))


def taxon_name(prim) -> str:
    """Taxon name for the given prim, if any."""
    return prim.GetAssetInfoByKey(_ASSETINFO_TAXON_KEY) or ""


def create_many(taxon, names, labels=tuple()) -> typing.List[Usd.Prim]:
    """Create a new taxon member for each of the provided names.

    a unit member of the given ``taxon``, with an optional display label.

    When creating hundreds of thousands of members, this provides a slight performance improvement (around 15% on average) over :func:`create`.

    The new members will be created as `prims <https://graphics.pixar.com/usd/docs/api/class_usd_prim.html>`_ on the given ``taxon``'s `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_.

    .. seealso:: :func:`define_taxon` :func:`create`
    """
    stage = taxon.GetStage()
    taxon_path = taxon.GetPath()
    taxon_fields = _get_id_fields(taxon)

    current_asset_name, root_layer = _root_asset(stage)
    new_asset_name = _names.UsdAsset(current_asset_name.get(**taxon_fields))
    # Edits will go to the first layer that matches a valid pipeline identifier
    # TODO: Evaluate if this agreement is robust enough for different workflows.

    # existing = {i.GetName() for i in _iter_taxa(taxon.GetStage(), *taxon.GetCustomDataByKey(_ASSETINFO_TAXA_KEY))}
    taxonomy_layer = _find_layer_matching(_TAXONOMY_FIELDS, stage.GetLayerStack())
    taxonomy_id = str(Path(taxonomy_layer.realPath).relative_to(Repository.get()))

    try:
        catalogue_layer = _find_layer_matching(_CATALOGUE_FIELDS, stage.GetLayerStack())
        catalogue_id = str(Path(catalogue_layer.realPath).relative_to(Repository.get()))
    except ValueError:  # first time adding the catalogue layer
        catalogue_asset = current_asset_name.get(**_CATALOGUE_FIELDS)
        catalogue_stage = fetch_stage(catalogue_asset)
        catalogue_layer = catalogue_stage.GetRootLayer()
        catalogue_id = str(Path(catalogue_layer.realPath).relative_to(Repository.get()))
        # Use paths relative to our repository to guarantee portability
        root_layer.subLayerPaths.insert(0, catalogue_id)

    # Some workflows like houdini might load layers without permissions to edit
    # Since we know we are in a valid pipeline layer, temporarily allow edits
    # for our operations, then restore original permissions.
    current_permission = catalogue_layer.permissionToEdit
    catalogue_layer.SetPermissionToEdit(True)

    scope_path = _CATALOGUE_ROOT_PATH.AppendChild(taxon.GetName())
    scope = stage.GetPrimAtPath(scope_path)

    def _create(name, label):
        path = scope_path.AppendChild(name)
        prim = stage.GetPrimAtPath(path)
        if prim:
            return prim
        assetid = new_asset_name.get(**{_UNIT_UNIQUE_ID.name: name})
        asset_stage = fetch_stage(assetid)
        # Deactivate "ourselves" as we are this item in the catalogue
        # TODO: this is experimental, see how reasonable / scalable this is
        # asset_stage.OverridePrim(path).SetActive(False)  # needed?
        asset_stage.CreateClassPrim(_CATALOGUE_ROOT_PATH)
        asset_layer = asset_stage.GetRootLayer()
        asset_layer.subLayerPaths.append(catalogue_id)
        asset_layer.subLayerPaths.append(taxonomy_id)
        asset_origin = asset_stage.DefinePrim(_UNIT_ORIGIN_PATH)
        # all catalogue units start as components
        Usd.ModelAPI(asset_origin).SetKind(Kind.Tokens.component)
        UsdGeom.ModelAPI.Apply(asset_origin)
        modelAPI = Usd.ModelAPI(asset_origin)
        modelAPI.SetAssetName(name)
        modelAPI.SetAssetIdentifier(str(assetid))
        asset_origin.GetInherits().AddInherit(taxon_path)
        asset_stage.SetDefaultPrim(asset_origin)
        if label:
            label_attr = asset_origin.GetAttribute("label")
            label_attr.Set(label)

        over_prim = stage.OverridePrim(path)
        over_prim.GetReferences().AddReference(asset_layer.identifier)
        return over_prim

    labels = itertools.chain(labels, itertools.repeat(""))
    with Usd.EditContext(stage, catalogue_layer):
        # Scope collecting all units based on taxon
        if not scope:
            scope = stage.DefinePrim(scope_path)
        if not scope.IsModel():
            # We use groups to ensure our scope is part of a valid model hierarchy
            for path in scope.GetPath().GetPrefixes():
                Usd.ModelAPI(stage.GetPrimAtPath(path)).SetKind(Kind.Tokens.group)
        prims = [_create(name, label) for name, label in zip(names, labels)]

    catalogue_layer.SetPermissionToEdit(current_permission)
    return prims


def create(taxon: Usd.Prim, name: str, label: str = "") -> Usd.Prim:
    """Create a unit member of the given ``taxon``, with an optional display label.

    The new member will be created as a `prim <https://graphics.pixar.com/usd/docs/api/class_usd_prim.html>`_ on the given ``taxon``'s `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_.

    .. seealso:: :func:`define_taxon` and :func:`create_many`
    """
    return create_many(taxon, [name], [label])[0]


def taxonomy_context(stage: Usd.Stage) -> Usd.EditContext:
    """Get an `edit context <https://graphics.pixar.com/usd/docs/api/class_usd_edit_context.html>`_ where edits will target this `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_'s taxonomy `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_.

    .. attention::
        If a valid taxonomy `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_ is not found on the `layer stack <https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-LayerStack>`_, one is added to the `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_.
    """
    try:
        taxonomy_layer = _find_layer_matching(_TAXONOMY_FIELDS, stage.GetLayerStack())
    except ValueError:
        # Our layer is not yet on the current layer stack. Let's bring it.
        # TODO: first valid pipeline layer is ok? or should it be current edit target?
        root_asset, root_layer = _root_asset(stage)
        taxonomy_asset = root_asset.get(**_TAXONOMY_FIELDS)
        taxonomy_stage = fetch_stage(taxonomy_asset)
        taxonomy_layer = taxonomy_stage.GetRootLayer()
        # Use paths relative to our repository to guarantee portability
        taxonomy_id = str(Path(taxonomy_layer.realPath).relative_to(Repository.get()))
        root_layer.subLayerPaths.append(taxonomy_id)

        if not taxonomy_stage.GetDefaultPrim():
            default_prim = taxonomy_stage.CreateClassPrim(_TAXONOMY_ROOT_PATH)
            taxonomy_stage.SetDefaultPrim(default_prim)

    return edit_context(stage, taxonomy_layer)


def unit_context(prim: Usd.Prim) -> Usd.EditContext:
    """Get an `edit context <https://graphics.pixar.com/usd/docs/api/class_usd_edit_context.html>`_ where edits will target this `prim <https://graphics.pixar.com/usd/docs/api/class_usd_prim.html>`_'s unit root `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_."""
    # This targets the origin prim spec as the "entry point" edit target for a unit of a taxon.
    # This means some operations like specializes, inherits or internal reference / payloads
    # might not be able to be resolved (you will se an error like:
    # 'Cannot map </Catalogue/OtherPlace/CastleDracula> to current edit target.'
    layer = unit_asset(prim)

    def target_predicate(node):
        return node.path == _UNIT_ORIGIN_PATH and node.layerStack.identifier.rootLayer == layer

    return edit_context(prim, _ASSET_UNIT_QUERY_FILTER, target_predicate)


def unit_asset(prim: Usd.Prim) -> Sdf.Layer:
    """Get the asset layer that acts as the 'entry point' for the given prim."""
    with Ar.ResolverContextBinder(prim.GetStage().GetPathResolverContext()):
        # Use Layer.Find since layer should have been open for the prim to exist.
        if layer := Sdf.Layer.Find(Usd.ModelAPI(prim).GetAssetIdentifier().path):
            return layer
    fields = {**_get_id_fields(prim), _UNIT_UNIQUE_ID: Usd.ModelAPI(prim).GetAssetName()}
    return _find_layer_matching(fields, prim.GetPrimStack())


def spawn_unit(parent, child, path=Sdf.Path.emptyPath):
    """Convenience function for bringing a unit prim as a descendant of another.

    - Both parent and child must be existing units in the catalogue.
    - If path is not provided, the name of child will be used.
    - Validity on model hierarchy is preserved by:
        - turning parent into an assembly
        - ensuring intermediate prims between parent and child are also models
    - By default, spawned units are instanceable
    """
    # this is because at the moment it is not straight forward to bring catalogue units under others.
    parent_stage = fetch_stage(Usd.ModelAPI(parent).GetAssetIdentifier().path, parent.GetStage().GetPathResolverContext())
    origin = parent_stage.GetDefaultPrim()
    relpath = path or child.GetName()
    path = origin.GetPath().AppendPath(relpath)
    # TODO: turn into function to ensure creation and query are the same?
    child_catalogue_unit_path = _CATALOGUE_ROOT_PATH.AppendChild(taxon_name(child)).AppendChild(Usd.ModelAPI(child).GetAssetName())
    spawned = parent_stage.DefinePrim(path)
    with Sdf.ChangeBlock():
        # Action of bringing a unit from our catalogue turns parent into an assembly
        Usd.ModelAPI(origin).SetKind(Kind.Tokens.assembly)
        # check for all intermediate parents of our spawned unit to ensure valid model hierarchy
        for inner_parent in _usd.iprims(origin.GetStage(), [origin.GetPath()], lambda p: p == spawned.GetParent()):
            if not inner_parent.IsModel():
                Usd.ModelAPI(inner_parent).SetKind(Kind.Tokens.group)
        # NOTE: Still experimenting to see if specializing from catalogue is a nice approach.
        spawned.GetSpecializes().AddSpecialize(child_catalogue_unit_path)
        spawned.SetInstanceable(True)
    return parent.GetPrimAtPath(relpath)


def _root_asset(stage):
    """From a give stage, find the first layer that matches a valid grill identifier.

    This can be useful in situations when a stage's root layer is not a valid identifier (e.g. anonymous) but
    has sublayered a valid one in the pipeline.

    This searches on the root layer first.
    """
    with contextlib.suppress(ValueError):
        root_layer = stage.GetRootLayer()
        return _names.UsdAsset(Path(root_layer.identifier).name), root_layer

    seen = set()
    for layer in stage.GetLayerStack():
        try:
            return _names.UsdAsset(Path(layer.identifier).name), layer
        except ValueError:
            seen.add(layer)
            continue
    raise ValueError(f"Could not find a valid pipeline layer for stage {stage}. Searched layer stack: {pformat(seen)}")


def _get_id_fields(prim):
    fields = prim.GetAssetInfoByKey(_ASSETINFO_FIELDS_KEY)
    if not fields:
        raise ValueError(f"Missing or empty '{_FIELDS_KEY}' on '{_ASSETINFO_KEY}' asset info for {prim}. Got: {pformat(prim.GetAssetInfoByKey(_ASSETINFO_KEY))}")
    if not isinstance(fields, typing.Mapping):
        raise TypeError(f"Expected mapping on key '{_FIELDS_KEY}' from {prim} on custom data key '{_ASSETINFO_KEY}'. Got instead {fields} with type: {type(fields)}")
    return fields


def _find_layer_matching(tokens: typing.Mapping, layers: typing.Iterable[Sdf.Layer]) -> Sdf.Layer:
    """Find the first layer matching the given identifier tokens.

    :raises ValueError: If none of the given layers match the provided tokens.
    """
    tokens = {
        ((token.name if isinstance(token, ids.CGAsset) else token), value)
        for token, value in tokens.items()
    }
    seen = set()
    for layer in layers:
        # anonymous layers realPath defaults to an empty string
        name = _names.UsdAsset(Path(layer.realPath).name)
        if tokens.difference(name.values.items()):
            seen.add(layer)
            continue
        return layer
    raise ValueError(f"Could not find layer matching {tokens}. Searched on:\n{pformat(seen)}")


@functools.singledispatch
def edit_context(obj, layer):
    """No doc"""
    raise TypeError(f"Not implemented: {locals()}")  # lazy


@edit_context.register
def _(stage: Usd.Stage, layer):
    """stage"""
    return Usd.EditContext(stage, layer)


@edit_context.register
def _(prim: Usd.Prim, query_filter, target_predicate):
    """Composition arcs target layer stacks. This is a convenience function to
    get an edit context from a query filter + a filter predicate, using the root layer
    of the matching target node as the edit target layer.
    """
    query = Usd.PrimCompositionQuery(prim)
    query.filter = query_filter
    for arc in query.GetCompositionArcs():
        if target_predicate(node := arc.GetTargetNode()):
            target = Usd.EditTarget(node.layerStack.identifier.rootLayer, node)
            return Usd.EditContext(prim.GetStage(), target)
    raise ValueError(f"Could not find appropriate node for edit target for {prim} matching {target_predicate}")


@edit_context.register
def _(payload: Sdf.Payload, prim):
    """Payload"""
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
    """variant set"""
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
