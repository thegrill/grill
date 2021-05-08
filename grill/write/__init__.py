from __future__ import annotations

import uuid
import types
import typing
import logging
import functools
import itertools
import contextvars
import collections

from pprint import pformat
from pathlib import Path
from pxr import UsdUtils, Usd, Sdf, Ar, Kind

import naming
from grill import names

logger = logging.getLogger(__name__)

repo = contextvars.ContextVar('repo')

_TAXONOMY_ROOT_PATH = Sdf.Path("/Taxonomy")
_TAXONOMY_FIELDS = dict(kingdom='taxonomy')


@functools.lru_cache(maxsize=None)
def fetch_stage(root_id) -> Usd.Stage:
    """For the given root layer identifier, get a corresponding stage.

    If layer does not exist, it is created in the repository.

    If a stage for the corresponding layer is found on the global cache, return it.
    Otherwise open it, populate the cache and return it.

    :param root_id:
    :return:
    """
    rootf = UsdAsset(root_id)
    cache = UsdUtils.StageCache.Get()
    repo_path = repo.get()
    resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])
    with Ar.ResolverContextBinder(resolver_ctx):
        layer_id = rootf.name
        logger.debug(f"Searching for {layer_id}")
        layer = Sdf.Layer.Find(layer_id)
        if not layer:
            logger.debug(f"Layer {layer_id} was not found open. Attempting to open it.")
            if not Sdf.Layer.FindOrOpen(layer_id):
                logger.debug(f"Layer {layer_id} does not exist on repository path: {resolver_ctx.GetSearchPath()}. Creating a new one.")
                # we first create a layer under our repo
                tmp_new_layer = Sdf.Layer.CreateNew(str(repo_path / layer_id))
                # delete it since it will have an identifier with the full path,
                # and we want to have the identifier relative to the repository path
                # TODO: with AR 2.0 it should be possible to create in memory layers
                #   with relative identifers to that of the search path of the context.
                #   In the meantime, we need to create the layer first on disk.
                del tmp_new_layer
            stage = Usd.Stage.Open(layer_id)
            logger.debug(f"Root layer: {stage.GetRootLayer()}")
            logger.debug(f"Opened stage: {stage}")
            cache_id = cache.Insert(stage)
            logger.debug(f"Added stage for {layer_id} with cache ID: {cache_id.ToString()}.")
        else:
            logger.debug(f"Layer was open. Found: {layer}")
            stage = cache.FindOneMatching(layer)
            if not stage:
                logger.debug(f"Could not find stage on the cache.")
                stage = Usd.Stage.Open(layer)
                cache_id = cache.Insert(stage)
                logger.debug(f"Added stage for {layer} with cache ID: {cache_id.ToString()}.")
            else:
                logger.debug(f"Found stage: {stage}")

    return stage


def define_taxon(stage: Usd.Stage, name:str, id_fields: typing.Mapping=types.MappingProxyType({}), references=tuple(),) -> Usd.Prim:
    """Define a new taxon group for asset taxonomy.

    If an existing taxon with the provided name already exists, it is returned.

    If id_fields is provided, it is set on the prim.

    If references are passed, they are added.
    """
    with taxonomy_context(stage):
        prim = stage.CreateClassPrim(_TAXONOMY_ROOT_PATH.AppendChild(name))
        for reference in references:
            prim.GetReferences().AddInternalReference(reference.GetPath())
        current = (prim.GetCustomDataByKey('grill') or {}).get('fields', {})
        prim.SetCustomDataByKey("grill", dict(fields={**id_fields, **current, 'kingdom':name}))
    return prim


def create(taxon: Usd.Prim, name, label=""):
    stage = taxon.GetStage()
    new_tokens = dict(taxon.GetCustomDataByKey('grill')['fields'], item=name)
    current_asset_name = UsdAsset(Path(stage.GetRootLayer().identifier).name)
    new_asset_name = current_asset_name.get(**new_tokens)

    # Scope collecting all assets of the same type
    scope_path = stage.GetPseudoRoot().GetPath().AppendPath(taxon.GetName())
    scope = stage.GetPrimAtPath(scope_path)
    if not scope:
        scope = stage.DefinePrim(scope_path)
    if not scope.IsModel():
        Usd.ModelAPI(scope).SetKind(Kind.Tokens.assembly)
    path = scope_path.AppendChild(name)
    if stage.GetPrimAtPath(path):
        return stage.GetPrimAtPath(path)

    asset_stage = fetch_stage(new_asset_name)
    asset_origin_path = Sdf.Path("/Origin")
    asset_origin = asset_stage.DefinePrim(asset_origin_path)
    category_layer = _find_layer_matching(_TAXONOMY_FIELDS, stage.GetLayerStack())
    category_layer_id = str(Path(category_layer.realPath).relative_to(repo.get()))
    asset_origin.GetReferences().AddReference(category_layer_id, taxon.GetPath())
    asset_stage.SetDefaultPrim(asset_origin)

    if label:
        label_attr = asset_origin.GetAttribute("label")
        if not label_attr.IsValid():
            # TODO: enforce this always?
            logger.debug(f"Invalid attribute: {label_attr}. Creating a new one on {asset_origin}")
            label_attr = asset_origin.CreateAttribute("label", Sdf.ValueTypeNames.String)

        label_attr.Set(label)

    over_prim = stage.OverridePrim(path)
    over_prim.GetPayloads().AddPayload(asset_stage.GetRootLayer().identifier)
    return over_prim


def context(obj, tokens):
    layers = reversed(list(_layer_stack(obj)))
    asset_layer = _find_layer_matching(tokens, layers)
    return _edit_context(obj, asset_layer)


def taxonomy_context(stage):
    try:
        return context(stage, _TAXONOMY_FIELDS)
    except ValueError:
        # Our layer is not yet on the current layer stack. Let's bring it.
        # TODO: root is ok? or should it be current edit target?
        root_layer = stage.GetRootLayer()
        root_asset = UsdAsset(Path(stage.GetRootLayer().identifier).name)
        taxonomy_asset = root_asset.get(**_TAXONOMY_FIELDS)
        taxonomy_stage = fetch_stage(taxonomy_asset)
        taxonomy_layer = taxonomy_stage.GetRootLayer()
        # Use paths relative to our repository to guarantee portability
        taxonomy_reference = str(Path(taxonomy_layer.realPath).relative_to(repo.get()))
        root_layer.subLayerPaths.append(taxonomy_reference)

        if not taxonomy_stage.GetDefaultPrim():
            taxonomy_stage.SetDefaultPrim(taxonomy_stage.DefinePrim(_TAXONOMY_ROOT_PATH))

        return context(stage, _TAXONOMY_FIELDS)


def asset_context(prim: Usd.Prim):
    fields = dict(prim.GetCustomDataByKey("grill")["fields"], item=prim.GetName())
    return context(prim, fields)


def _find_layer_matching(tokens: typing.Mapping, layers: typing.Iterable[Sdf.Layer]) -> Sdf.Layer:
    """Find the first layer matching the given identifier tokens.

    :raises ValueError: If none of the given layers match the provided tokens.
    """
    tokens = set(tokens.items())
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
    return (spec.layer for spec in obj.GetPrimStack())


@_layer_stack.register
def _(obj: Usd.Property):
    return (spec.layer for spec in obj.GetPropertyStack())


class UsdAsset(names.CGAssetFile):
    DEFAULT_SUFFIX = 'usda'
    file_config = naming.NameConfig(
        {'suffix': "|".join(Sdf.FileFormat.FindAllFileFormatExtensions())}
    )

    @classmethod
    def get_anonymous(cls, **values) -> UsdAsset:
        """Get an anonymous USD file name with optional field overrides.

        Generally useful for situation where a temporary but valid identifier is needed.

        :param values: Variable keyword arguments with the keys referring to the name's
            fields which will use the given values.

        Example:
            >>> UsdAsset.get_anonymous(stream='test')
            UsdAsset("4209091047-34604-19646-169-123-test-4209091047-34604-19646-169.1.usda")

        """
        keys = cls.get_default().get_pattern_list()
        anon = itertools.cycle(uuid.uuid4().fields)
        return cls.get_default(**collections.ChainMap(values, dict(zip(keys, anon))))
