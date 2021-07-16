"""Authoring and editing foundational tools for the pipeline.

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

_PRIM_GRILL_KEY = 'grill'
_PRIM_FIELDS_KEY = 'fields'
_PRIM_TAXA_KEY = 'taxa'

# Taxonomy rank handles the grill classification and grouping of assets.
_TAXONOMY_NAME = 'Taxonomy'
_TAXONOMY_ROOT_PATH = Sdf.Path.absoluteRootPath.AppendChild(_TAXONOMY_NAME)
_TAXONOMY_UNIQUE_ID = ids.CGAsset.cluster  # High level organization of our assets.
_TAXONOMY_FIELDS = types.MappingProxyType({_TAXONOMY_UNIQUE_ID.name: _TAXONOMY_NAME})
_UNIT_UNIQUE_ID = ids.CGAsset.item  # Entry point for meaningful composed assets.
_UNIT_ORIGIN_PATH = Sdf.Path("/Origin")


@functools.lru_cache(maxsize=None)
def fetch_stage(identifier: str) -> Usd.Stage:
    """Retrieve the `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_ whose root `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_ matches the given ``identifier``.

    If the `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_ does not exist, it is created in the repository.

    If an open matching `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_ is found on the `global cache <https://graphics.pixar.com/usd/docs/api/class_usd_utils_stage_cache.html>`_, return it.
    Otherwise open it, populate the `cache <https://graphics.pixar.com/usd/docs/api/class_usd_utils_stage_cache.html>`_ and return it.
    """
    layer_id = UsdAsset(identifier).name
    cache = UsdUtils.StageCache.Get()
    repo_path = Repository.get()
    resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])
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
        prim = stage.CreateClassPrim(_TAXONOMY_ROOT_PATH.AppendChild(name))
        for reference in references:
            prim.GetReferences().AddInternalReference(reference.GetPath())
        prim.CreateAttribute("label", Sdf.ValueTypeNames.String, custom=False)
        taxon_fields = {**fields, _TAXONOMY_UNIQUE_ID.name: name}
        prim.SetCustomDataByKey(_PRIM_GRILL_KEY, {_PRIM_FIELDS_KEY: taxon_fields, _PRIM_TAXA_KEY: {name: 0}})

    return prim


def _iter_taxa(stage, taxon1, *taxonN, predicate=Usd.PrimDefaultPredicate):
    """Iterate over prims that inherit from the given taxa."""
    it = iter(Usd.PrimRange.Stage(stage, predicate=predicate))
    taxa_names = {i if isinstance(i, str) else i.GetName() for i in (taxon1, *taxonN)}
    for prim in it:
        if prim.GetPath().HasPrefix(_TAXONOMY_ROOT_PATH):
            # Ignore prims from the taxonomy hierarchy as they're not
            # taxa members but the definition themselves.
            it.PruneChildren()
        elif taxa_names.intersection(prim.GetCustomDataByKey(f'{_PRIM_GRILL_KEY}:{_PRIM_TAXA_KEY}') or {}):
            yield prim


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

    # Some workflows like houdini might load layers without permissions to edit
    # Since we know we are in a valid pipeline layer, temporarily allow edits
    # for our operations, then restore original permissions.
    current_permission = root_layer.permissionToEdit
    root_layer.SetPermissionToEdit(True)

    # existing = {i.GetName() for i in _iter_taxa(taxon.GetStage(), *taxon.GetCustomDataByKey(f'{_PRIM_GRILL_KEY}:{_PRIM_TAXA_KEY}'))}
    taxonomy_layer = _find_layer_matching(_TAXONOMY_FIELDS, stage.GetLayerStack())
    # taxonomy_layer_id = str(Path(taxonomy_layer.realPath).relative_to(Repository.get()))
    taxonomy_layer_id = taxonomy_layer.identifier  # TODO: please ensure it's never absolute path

    scope_path = stage.GetPseudoRoot().GetPath().AppendPath(taxon.GetName())
    scope = stage.GetPrimAtPath(scope_path)

    def _create(name, label):
        path = scope_path.AppendChild(name)
        prim = stage.GetPrimAtPath(path)
        if prim:
            return prim
        assetid = new_asset_name.get(**{_UNIT_UNIQUE_ID.name: name})
        asset_stage = fetch_stage(assetid)
        asset_origin = asset_stage.DefinePrim(_UNIT_ORIGIN_PATH)
        asset_origin.GetReferences().AddReference(taxonomy_layer_id, taxon_path)
        asset_stage.SetDefaultPrim(asset_origin)
        if label:
            label_attr = asset_origin.GetAttribute("label")
            label_attr.Set(label)

        over_prim = stage.OverridePrim(path)
        over_prim.GetPayloads().AddPayload(
            asset_stage.GetRootLayer().identifier)
        return over_prim

    labels = itertools.chain(labels, itertools.repeat(""))
    with Usd.EditContext(stage, root_layer):
        # Scope collecting all assets of the same type
        if not scope:
            scope = stage.DefinePrim(scope_path)
        if not scope.IsModel():
            Usd.ModelAPI(scope).SetKind(Kind.Tokens.assembly)
        prims = [_create(name, label) for name, label in zip(names, labels)]

    root_layer.SetPermissionToEdit(current_permission)
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
        taxonomy_reference = str(Path(taxonomy_layer.realPath).relative_to(Repository.get()))
        root_layer.subLayerPaths.append(taxonomy_reference)

        if not taxonomy_stage.GetDefaultPrim():
            taxonomy_stage.SetDefaultPrim(taxonomy_stage.DefinePrim(_TAXONOMY_ROOT_PATH))

        return _context(stage, _TAXONOMY_FIELDS)


def unit_context(prim: Usd.Prim) -> Usd.EditContext:
    """Get an `edit context <https://graphics.pixar.com/usd/docs/api/class_usd_edit_context.html>`_ where edits will target this `prim <https://graphics.pixar.com/usd/docs/api/class_usd_prim.html>`_'s unit root `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_."""
    fields = {**_get_id_fields(prim), _UNIT_UNIQUE_ID: prim.GetName()}
    return _context(prim, fields)


def unit_asset(prim: Usd.Prim) -> Sdf.Layer:
    """Get the asset layer that acts as the 'entry point' for the given prim."""
    fields = {**_get_id_fields(prim), _UNIT_UNIQUE_ID: prim.GetName()}
    return _find_layer_matching(fields, _layer_stack(prim))


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
    data = prim.GetCustomDataByKey(_PRIM_GRILL_KEY) or {}
    if not data:
        raise ValueError(f"No data found on '{_PRIM_GRILL_KEY}' key for {prim}")
    fields = data.get(_PRIM_FIELDS_KEY, {})
    if not fields:
        raise ValueError(f"Missing or empty '{_PRIM_FIELDS_KEY}' found on '{_PRIM_GRILL_KEY}' custom data for {prim}. Custom data: {pformat(data)}")
    if not isinstance(fields, typing.Mapping):
        raise TypeError(f"Expected mapping on key '{_PRIM_FIELDS_KEY}' from {prim} on custom data key '{_PRIM_GRILL_KEY}'. Got instead {fields} with type: {type(fields)}")
    return fields


def _context(obj, tokens):
    # TODO: do we need to reverse the order of the layer stack?
    #   at the moment, goes from strongest -> weakest layers
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
    # We need to explicitely construct our edit target since our layer is not on the layer stack of the stage.
    target = Usd.EditTarget(layer, obj.GetPrimIndex().rootNode.children[0])
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
