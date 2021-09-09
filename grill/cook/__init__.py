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

import uuid
import types
import typing
import logging
import functools
import itertools
import contextlib
import contextvars
import collections
from pathlib import Path
from pprint import pformat

import naming
from pxr import UsdUtils, Usd, Sdf, Ar, Kind
from grill import names
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
    """
    layer_id = UsdAsset(identifier).name
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
    new_asset_name = UsdAsset(current_asset_name.get(**taxon_fields))
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
        # Scope collecting all assets of the same type
        if not scope:
            scope = stage.DefinePrim(scope_path)
        if not scope.IsModel():
            Usd.ModelAPI(scope).SetKind(Kind.Tokens.assembly)
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
        return _context(stage, _TAXONOMY_FIELDS)
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

        return _context(stage, _TAXONOMY_FIELDS)


def unit_context(prim: Usd.Prim) -> Usd.EditContext:
    """Get an `edit context <https://graphics.pixar.com/usd/docs/api/class_usd_edit_context.html>`_ where edits will target this `prim <https://graphics.pixar.com/usd/docs/api/class_usd_prim.html>`_'s unit root `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_."""
    fields = {**_get_id_fields(prim), _UNIT_UNIQUE_ID: Usd.ModelAPI(prim).GetAssetName() or ""}
    return _context(prim, fields)


def unit_asset(prim: Usd.Prim) -> Sdf.Layer:
    """Get the asset layer that acts as the 'entry point' for the given prim."""
    fields = {**_get_id_fields(prim), _UNIT_UNIQUE_ID: prim.GetName()}
    return _find_layer_matching(fields, _layer_stack(prim))


def spawn_unit(parent, child, path=Sdf.Path.emptyPath):
    """Convenience function for bringing a unit prim as a descendant of another.

    - Both parent and child must be existing units in the catalogue.
    - If path is not provided, the name of child will be used.
    """
    # this is because at the moment it is not straight forward to bring catalogue units under others.
    parent_stage = fetch_stage(Usd.ModelAPI(parent).GetAssetIdentifier().path, parent.GetStage().GetPathResolverContext())
    origin = parent_stage.GetDefaultPrim()
    path = origin.GetPath().AppendPath(path or child.GetName())
    # TODO: turn into function to ensure creation and query are the same?
    child_catalogue_unit_path = _CATALOGUE_ROOT_PATH.AppendChild(taxon_name(child)).AppendChild(Usd.ModelAPI(child).GetAssetName())
    with unit_context(origin):
        spawned = parent_stage.DefinePrim(path)
        # NOTE: Experimenting to see if specializing from catalogue is a nice approach.
        # TODO: use model hierarchy here?
        spawned.GetSpecializes().AddSpecialize(child_catalogue_unit_path)


def _root_asset(stage):
    """From a give stage, find the first layer that matches a valid grill identifier.

    This can be useful in situations when a stage's root layer is not a valid identifier (e.g. anonymous) but
    has sublayered a valid one in the pipeline.

    This searches on the root layer first.
    """
    with contextlib.suppress(ValueError):
        root_layer = stage.GetRootLayer()
        return UsdAsset(Path(root_layer.identifier).name), root_layer

    seen = set()
    for layer in stage.GetLayerStack():
        try:
            return UsdAsset(Path(layer.identifier).name), layer
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


def _context(obj, tokens):
    # TODO: do we need to reverse the order of the layer stack?
    #   at the moment, goes from strongest -> weakest layers
    if not tokens:
        raise ValueError(f"Expected a valid populated mapping as 'tokens'. Got instad: '{tokens}'")
    layers = _layer_stack(obj)
    asset_layer = _find_layer_matching(tokens, layers)
    return _edit_context(obj, asset_layer)


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
        name = UsdAsset(Path(layer.realPath).name)
        if tokens.difference(name.values.items()):
            seen.add(layer)
            continue
        return layer
    raise ValueError(f"Could not find layer matching {tokens}. Searched on:\n{pformat(seen)}")


@functools.singledispatch
def _edit_context(obj, stage):
    raise TypeError(f"Not implemented: {locals()}")  # lazy


@_edit_context.register
def _(obj: Usd.Stage, layer):
    return Usd.EditContext(obj, layer)


@_edit_context.register
def _(obj: Usd.Prim, layer):
    # We need to explicitly construct our edit target since our layer is not on the layer stack of the stage.
    # TODO: this is specific about "localised edits" for an asset. Dispatch no longer looking solid?
    # Warning: this targets the origin prim spec as the "entry point" edit target for a unit of a taxon.
    # This means some operations like specializes, inherits or internal reference / payloads
    # might not be able to be resolved (you will se an error like:
    # 'Cannot map </Catalogue/OtherPlace/CastleDracula> to current edit target.'
    query = Usd.PrimCompositionQuery(obj)
    query.filter = _ASSET_UNIT_QUERY_FILTER
    logger.debug(f"Searching for {layer=}")
    for arc in query.GetCompositionArcs():
        target_node = arc.GetTargetNode()
        # contract: we consider the "unit" target node the one matching origin path and the given layer
        if target_node.path == _UNIT_ORIGIN_PATH and target_node.layerStack.identifier.rootLayer == layer:
            break
    else:
        raise ValueError(f"Could not find appropriate node for edit target for {obj} matching {layer}")
    target = Usd.EditTarget(layer, target_node)
    return Usd.EditContext(obj.GetStage(), target)


@functools.singledispatch
def _layer_stack(obj):
    raise TypeError(f"Not implemented: {obj}")  # lazy


@_layer_stack.register
def _(obj: Usd.Stage):
    return obj.GetLayerStack()


@_layer_stack.register
def _(obj: Usd.Prim):
    seen = set()
    for spec in obj.GetPrimStack():
        layer = spec.layer
        if layer in seen:
            continue
        seen.add(layer)
        yield layer


class UsdAsset(names.CGAssetFile):
    """Specialized :class:`grill.names.CGAssetFile` name object for USD asset resources.

    .. admonition:: Inheritance Diagram
        :class: dropdown, hint

        .. inheritance-diagram:: grill.write.UsdAsset

    This is the currency for "identifiers" in the pipeline.

    Examples:
        >>> asset_id = UsdAsset.get_default()
        >>> asset_id
        UsdAsset("demo-3d-abc-entity-rnd-main-atom-lead-base-whole.1.usda")
        >>> asset_id.suffix = 'usdc'
        >>> asset_id.version = 42
        >>> asset_id
        UsdAsset("demo-3d-abc-entity-rnd-main-atom-lead-base-whole.42.usdc")
        >>> asset_id.suffix = 'abc'
        Traceback (most recent call last):
        ...
        ValueError: Can't set invalid name 'demo-3d-abc-entity-rnd-main-atom-lead-base-whole.42.abc' on UsdAsset("demo-3d-abc-entity-rnd-main-atom-lead-base-whole.42.usdc"). Valid convention is: '{code}-{media}-{kingdom}-{cluster}-{area}-{stream}-{item}-{step}-{variant}-{part}.{pipe}.{suffix}' with pattern: '^(?P<code>\w+)\-(?P<media>\w+)\-(?P<kingdom>\w+)\-(?P<cluster>\w+)\-(?P<area>\w+)\-(?P<stream>\w+)\-(?P<item>\w+)\-(?P<step>\w+)\-(?P<variant>\w+)\-(?P<part>\w+)(?P<pipe>(\.(?P<output>\w+))?\.(?P<version>\d+)(\.(?P<index>\d+))?)(\.(?P<suffix>sdf|usd|usda|usdc|usdz))$'

    .. seealso::
        :class:`grill.names.CGAsset` for a description of available fields, :class:`naming.Name` for an overview of the core API.

    """
    DEFAULT_SUFFIX = 'usda'
    file_config = naming.NameConfig(
        # NOTE: limit to only extensions starting with USD (some environments register other extensions untested by the grill)
        {'suffix': "|".join(ext for ext in Sdf.FileFormat.FindAllFileFormatExtensions() if ext.startswith('usd'))}
    )

    @classmethod
    def get_anonymous(cls, **values) -> UsdAsset:
        """Get an anonymous :class:`UsdAsset` name with optional field overrides.

        Useful for situations where a temporary but valid identifier is needed.

        :param values: Variable keyword arguments with the keys referring to the name's
            fields which will use the given values.

        Example:
            >>> UsdAsset.get_anonymous(stream='test')
            UsdAsset("4209091047-34604-19646-169-123-test-4209091047-34604-19646-169.1.usda")

        """
        keys = cls.get_default().get_pattern_list()
        anon = itertools.cycle(uuid.uuid4().fields)
        return cls.get_default(**collections.ChainMap(values, dict(zip(keys, anon))))
