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
_ASSET_TOKENS = types.MappingProxyType(dict(kingdom="asset"))
_CATEGORY_TOKENS = types.MappingProxyType(dict(kingdom="category",))
_CATEGORY_ROOT_PATH = Sdf.Path("/Category")


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


def define_category(stage: Usd.Stage, name: str, references=tuple()) -> Usd.Prim:
    db_type_path = _CATEGORY_ROOT_PATH.AppendChild(name)
    db_type = stage.GetPrimAtPath(db_type_path)
    if db_type:
        return db_type

    # Use class prims since we want db types to be abstract.
    with category_context(stage):
        db_type = stage.CreateClassPrim(db_type_path)
        for reference in references:
            db_type.GetReferences().AddInternalReference(reference.GetPath())

    return stage.GetPrimAtPath(db_type_path)


def find_layer_matching(tokens: typing.Mapping, layers: typing.Iterable[Sdf.Layer]) -> Sdf.Layer:
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


def create(category: Usd.Prim, name, display_name=""):
    """Whenever we create a new item from the database, make it it's own entity"""
    stage = category.GetStage()
    new_tokens = dict(_ASSET_TOKENS, cluster=category.GetName(), item=name)
    # contract: all categorys have a display_name
    current_asset_name = UsdAsset(Path(stage.GetRootLayer().identifier).name)
    new_asset_name = current_asset_name.get(**new_tokens)

    # Scope collecting all assets of the same type
    scope_path = stage.GetPseudoRoot().GetPath().AppendPath(category.GetName())
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
    asset_origin = asset_stage.GetPrimAtPath(asset_origin_path)
    if not asset_origin:
        asset_origin = asset_stage.DefinePrim(asset_origin_path)
        category_layer = find_layer_matching(_CATEGORY_TOKENS, stage.GetLayerStack())
        category_layer_id = str(Path(category_layer.realPath).relative_to(repo.get()))
        asset_origin.GetReferences().AddReference(category_layer_id, category.GetPath())

    asset_stage.SetDefaultPrim(asset_origin)

    if display_name:
        display_attr = asset_origin.GetAttribute("display_name")
        if not display_attr.IsValid():
            # TODO: enforce this always?
            logger.debug(f"Invalid attribute: {display_attr}. Creating a new one on {asset_origin}")
            display_attr = asset_origin.CreateAttribute("display_name", Sdf.ValueTypeNames.String)

        display_attr.Set(display_name)

    over_prim = stage.OverridePrim(path)
    over_prim.GetPayloads().AddPayload(asset_stage.GetRootLayer().identifier)
    return over_prim


@functools.singledispatch
def edit_context(obj, stage):
    raise TypeError(f"Not implemented: {locals()}")  # lazy


@edit_context.register
def _(obj: Sdf.Layer, stage):
    return Usd.EditContext(stage, obj)


@edit_context.register
def _(obj: Usd.Prim, layer, stage):
    # We need to explicitely construct our edit target since our layer is not on the layer stack of the stage.
    target = Usd.EditTarget(layer, obj.GetPrimIndex().rootNode.children[0])
    return Usd.EditContext(stage, target)


def category_context(stage):
    """Edits go to the category root stage."""
    try:
        layer = find_layer_matching(_CATEGORY_TOKENS, stage.GetLayerStack())
    except ValueError:
        # Our layer is not yet on the current layer stack. Let's bring it.
        stage_layer = stage.GetRootLayer()
        current_asset_name = UsdAsset(Path(stage.GetRootLayer().identifier).name)
        # TODO: this is probably incorrect, should we get a category name for all the project?
        category_name = current_asset_name.get(**_CATEGORY_TOKENS)
        category_stage = fetch_stage(category_name)
        category_layer = category_stage.GetRootLayer()
        # TODO: There's a slight chance that the identifier is not a relative one.
        #   Ensure we don't author absolute paths here. It should all be relative
        #   to a path in our search path from the current resolver context.
        #   If it's not happening, we need to manually create a relative asset path
        #   str(Path(category_layer.identifier).relative_to(repo))
        # category_layer_id = str(Path(category_layer.realPath).relative_to(repo.get()))
        category_layer_id = category_layer.identifier
        stage_layer.subLayerPaths.append(category_layer_id)

        if not category_stage.GetDefaultPrim():
            category_stage.SetDefaultPrim(category_stage.DefinePrim(_CATEGORY_ROOT_PATH))
        layer = find_layer_matching(_CATEGORY_TOKENS, stage.GetLayerStack())
    return edit_context(layer, stage)


def asset_context(prim: Usd.Prim):
    layerstack = (stack.layer for stack in reversed(prim.GetPrimStack()))
    asset_layer = find_layer_matching(_ASSET_TOKENS, layerstack)
    return edit_context(prim, asset_layer, prim.GetStage())
