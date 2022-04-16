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

from pxr import UsdGeom, UsdUI, Usd, Sdf, Kind, Ar

from grill.tokens import ids
from grill.names import UsdAsset

from .. import usd as _usd

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


def _fetch_layer(identifier: str, context: Ar.ResolverContext) -> Sdf.Layer:
    """Retrieve `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_ for the given ``identifier``.

     If the `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_ does not exist, it is created in the repository.
     """
    if not (layer := Sdf.Layer.Find(identifier) or Sdf.Layer.FindOrOpen(identifier)):
        # TODO: see how to make this repo_path better, seems very experimental atm.
        repo_path = Path(context.Get()[0].GetSearchPath()[0])
        Sdf.Layer.CreateNew(str(repo_path / identifier))
        if not (layer:=Sdf.Layer.FindOrOpen(identifier)):
            raise RuntimeError("Make sure a resolver context with statement is being used.")
    return layer


@typing.overload
def fetch_stage(identifier: str, context: Ar.ResolverContext = None, load=Usd.Stage.LoadAll) -> Usd.Stage:
    ...


@typing.overload
def fetch_stage(identifier: "grill.names.UsdAsset", context: Ar.ResolverContext = None, load=Usd.Stage.LoadAll) -> Usd.Stage:
    ...  # TODO: evaluate if it's worth to keep this, or if identifier can be a relative path


# TODO: This used to be cached, evaluate if it's useful and bring it back if yes.
#       Cache was disabled since stages would remain open and listen to edits to other layers,
#       even if other places in the code did not have a reference to those stages.
@functools.singledispatch
def fetch_stage(identifier, context: Ar.ResolverContext = None, load=Usd.Stage.LoadAll) -> Usd.Stage:
    """Retrieve the `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_ whose root `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_ matches the given ``identifier``.

    If the `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_ does not exist, it is created in the repository.

    If an open matching `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_ is found on the `global cache <https://graphics.pixar.com/usd/docs/api/class_usd_utils_stage_cache.html>`_, return it.
    Otherwise open it, populate the `cache <https://graphics.pixar.com/usd/docs/api/class_usd_utils_stage_cache.html>`_ and return it.

    .. attention::
        ``identifier`` must be a valid :class:`grill.names.UsdAsset` name.

    """
    if not context:
        context = Ar.ResolverContext(Ar.DefaultResolverContext([str(Repository.get())]))

    with Ar.ResolverContextBinder(context):
        layer = _fetch_layer(identifier, context)
        return Usd.Stage.Open(layer, load=load)


@fetch_stage.register(UsdAsset)
def _(identifier: UsdAsset, *args, **kwargs) -> Usd.Stage:
    return fetch_stage.registry[object](identifier.name, *args, **kwargs)


@fetch_stage.register(str)
def _(identifier: str, *args, **kwargs) -> Usd.Stage:
    return fetch_stage(UsdAsset(identifier), *args, **kwargs)


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
    if intersection:=reserved_fields.intersection(id_fields):
        raise ValueError(f"Can not provide reserved id fields: {', '.join(map(str, intersection))}. Got fields: {', '.join(map(str, id_fields))}")

    fields = {
        (token.name if isinstance(token, ids.CGAsset) else token): value
        for token, value in id_fields.items()
    }
    if invalid_fields:=set(fields).difference(ids.CGAsset.__members__):
        raise ValueError(f"Got invalid id_field keys: {', '.join(invalid_fields)}. Allowed: {', '.join(ids.CGAsset.__members__)}")

    with taxonomy_context(stage):
        prim = stage.DefinePrim(_TAXONOMY_ROOT_PATH.AppendChild(name))
        for reference in references:
            prim.GetReferences().AddInternalReference(reference.GetPath())
        taxon_fields = {**fields, _TAXONOMY_UNIQUE_ID.name: name}
        prim.SetAssetInfoByKey(_ASSETINFO_KEY, {_FIELDS_KEY: taxon_fields, _TAXA_KEY: {name: 0}})

    return prim


def itaxa(prims, taxon, *taxa):
    """Yields prims that are part of the given taxa."""
    taxa_names = {i if isinstance(i, str) else i.GetName() for i in (taxon, *taxa)}
    return (prim for prim in prims if taxa_names.intersection(prim.GetAssetInfoByKey(_ASSETINFO_TAXA_KEY) or {}))


def _catalogue_path(taxon):
    taxon_fields = _get_id_fields(taxon)
    relpath = taxon_fields[_TAXONOMY_UNIQUE_ID.name]
    if _CATALOGUE_ID.name in taxon_fields:  # TODO: ensure this can't be overwritten
        relpath = f"{taxon_fields[_CATALOGUE_ID.name]}/{relpath}"
    return _CATALOGUE_ROOT_PATH.AppendPath(relpath)


def create_many(taxon, names, labels=tuple()) -> typing.List[Usd.Prim]:
    """Create a new taxon member for each of the provided names.

    When creating hundreds or thousands of members, this provides a considerable performance improvement over :func:`create_unit`.

    The new members will be created as `prims <https://graphics.pixar.com/usd/docs/api/class_usd_prim.html>`_ on the given ``taxon``'s `stage <https://graphics.pixar.com/usd/docs/api/class_usd_stage.html>`_.

    .. seealso:: :func:`define_taxon` :func:`create_unit`
    """
    stage = taxon.GetStage()
    taxon_path = taxon.GetPath()
    taxon_fields = _get_id_fields(taxon)
    scope_path = _catalogue_path(taxon)

    current_asset_name, root_layer = _root_asset(stage)
    new_asset_name = UsdAsset(current_asset_name.get(**taxon_fields))
    # Edits will go to the first layer that matches a valid pipeline identifier
    # TODO: Evaluate if this agreement is robust enough for different workflows.

    # existing = {i.GetName() for i in _iter_taxa(taxon.GetStage(), *taxon.GetCustomDataByKey(_ASSETINFO_TAXA_KEY))}
    taxonomy_layer = _find_layer_matching(_TAXONOMY_FIELDS, stage.GetLayerStack())
    taxonomy_id = str(Path(taxonomy_layer.realPath).relative_to(Repository.get()))
    context = stage.GetPathResolverContext()

    try:
        catalogue_layer = _find_layer_matching(_CATALOGUE_FIELDS, stage.GetLayerStack())
        catalogue_id = str(Path(catalogue_layer.realPath).relative_to(Repository.get()))
    except ValueError:  # first time adding the catalogue layer
        catalogue_asset = current_asset_name.get(**_CATALOGUE_FIELDS)
        with Ar.ResolverContextBinder(context):
            catalogue_layer = _fetch_layer(str(catalogue_asset), context)
        catalogue_id = str(Path(catalogue_layer.realPath).relative_to(Repository.get()))
        # Use paths relative to our repository to guarantee portability
        root_layer.subLayerPaths.insert(0, catalogue_id)

    # Some workflows like houdini might load layers without permissions to edit
    # Since we know we are in a valid pipeline layer, temporarily allow edits
    # for our operations, then restore original permissions.
    current_permission = catalogue_layer.permissionToEdit
    catalogue_layer.SetPermissionToEdit(True)

    scope = stage.GetPrimAtPath(scope_path)
    # THOUGHT:
    # Do not sublayer catalogue / taxonomy by default, as those are needed for "working context" only?
    # PRO: allows for nice specializes workflow, but then, what's the advantage over internal reference?
    # CON: units are not self contained by open in usdview.

    # THOUGHT PART 2:
    # anchor is created for pulling
    def _fetch_layer_for_unit(name):
        unit_tokens = {_UNIT_UNIQUE_ID.name: name}
        whole_id = new_asset_name.get(**unit_tokens)
        # whole: the self contained entry point for the new unit
        target_id = new_asset_name.get(**unit_tokens, **{ids.CGAsset.part.name: "target"})
        # target: the target entry point for referencing this unit in the pipeline

        target_layer = _fetch_layer(target_id, context)

        # -------- TODO: Sublayering Catalogue is experimental, see how reasonable / scalable this is --------#
        whole_layer = _fetch_layer(whole_id, context)
        whole_layer.subLayerPaths.append(catalogue_id)
        whole_layer.subLayerPaths.append(taxonomy_id)
        whole_layer.subLayerPaths.append(target_id)
        Sdf.CreatePrimInLayer(whole_layer, _CATALOGUE_ROOT_PATH).specifier = Sdf.SpecifierClass
        whole_layer.Save()

        # -------------
        target_layer.subLayerPaths.append(catalogue_id)
        target_layer.subLayerPaths.append(taxonomy_id)
        # whole_layer.subLayerPaths.append(target_id)
        Sdf.CreatePrimInLayer(target_layer, _CATALOGUE_ROOT_PATH).specifier = Sdf.SpecifierClass
        # -------------

        origin = Sdf.CreatePrimInLayer(target_layer, _UNIT_ORIGIN_PATH)
        origin.specifier = Sdf.SpecifierDef
        origin.inheritPathList.Prepend(taxon_path)
        target_layer.defaultPrim = origin.name
        return target_layer, whole_layer

    labels = itertools.chain(labels, itertools.repeat(""))
    with Usd.EditContext(stage, catalogue_layer), Ar.ResolverContextBinder(context):
        # Scope collecting all units based on taxon
        if not scope:
            scope = stage.DefinePrim(scope_path)
        if not scope.IsModel():
            # We use groups to ensure our scope is part of a valid model hierarchy
            for path in scope.GetPath().GetPrefixes():
                Usd.ModelAPI(stage.GetPrimAtPath(path)).SetKind(Kind.Tokens.group)

        with Sdf.ChangeBlock():
            prims_info = []
            for name, label in zip(names, labels):
                if not stage.GetPrimAtPath(path:=scope_path.AppendChild(name)):
                    stage.OverridePrim(path)
                target_layer, whole_layer = _fetch_layer_for_unit(name)
                prims_info.append((name, label or name, path, target_layer, whole_layer, Sdf.Reference(target_layer.identifier)))

        prims_info = {stage.GetPrimAtPath(info[2]): info for info in prims_info}
        with Sdf.ChangeBlock():
            for prim, (name, *__, whole_layer, reference) in prims_info.items():
                prim.GetReferences().AddReference(reference)
                with _usd.edit_context(reference, prim):
                    UsdUI.SceneGraphPrimAPI.Apply(prim)
                    UsdGeom.ModelAPI.Apply(prim)
                    modelAPI = Usd.ModelAPI(prim)
                    modelAPI.SetKind(Kind.Tokens.component)
                    modelAPI.SetAssetName(name)
                    modelAPI.SetAssetIdentifier(whole_layer.identifier)

        with Sdf.ChangeBlock():
            for prim, (name, label, *__, reference) in prims_info.items():
                with _usd.edit_context(reference, prim):
                    UsdUI.SceneGraphPrimAPI(prim).GetDisplayNameAttr().Set(label or name)

    catalogue_layer.SetPermissionToEdit(current_permission)
    return list(prims_info)


def create_unit(taxon: Usd.Prim, name: str, label: str = "") -> Usd.Prim:
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
    # https://en.wikipedia.org/wiki/Taxonomy_(biology)
    try:
        taxonomy_layer = _find_layer_matching(_TAXONOMY_FIELDS, stage.GetLayerStack())
    except ValueError:
        # Our layer is not yet on the current layer stack. Let's bring it.
        # TODO: first valid pipeline layer is ok? or should it be current edit target?
        root_asset, root_layer = _root_asset(stage)
        taxonomy_asset = root_asset.get(**_TAXONOMY_FIELDS)
        with Ar.ResolverContextBinder(context:=stage.GetPathResolverContext()):
            taxonomy_layer = _fetch_layer(str(taxonomy_asset), context)
        # Use paths relative to our repository to guarantee portability
        taxonomy_id = str(Path(taxonomy_layer.realPath).relative_to(Repository.get()))
        taxonomy_root = Sdf.CreatePrimInLayer(taxonomy_layer, _TAXONOMY_ROOT_PATH)
        taxonomy_root.specifier = Sdf.SpecifierClass
        taxonomy_layer.defaultPrim = taxonomy_root.name
        root_layer.subLayerPaths.append(taxonomy_id)

    return Usd.EditContext(stage, taxonomy_layer)


def unit_context(prim: Usd.Prim) -> Usd.EditContext:
    """Get an `edit context <https://graphics.pixar.com/usd/docs/api/class_usd_edit_context.html>`_ where edits will target this `prim <https://graphics.pixar.com/usd/docs/api/class_usd_prim.html>`_'s unit root `layer <https://graphics.pixar.com/usd/docs/api/class_sdf_layer.html>`_."""
    # This targets the origin prim spec as the "entry point" edit target for a unit of a taxon.
    # This means some operations like specializes, inherits or internal reference / payloads
    # might not be able to be resolved (you will se an error like:
    # 'Cannot map </Catalogue/OtherPlace/CastleDracula> to current edit target.'
    layer = unit_asset(prim)

    def target_predicate(node):
        return node.path == _UNIT_ORIGIN_PATH and node.layerStack.identifier.rootLayer == layer

    return _usd.edit_context(prim, _ASSET_UNIT_QUERY_FILTER, target_predicate)


def unit_asset(prim: Usd.Prim) -> Sdf.Layer:
    """Get the asset layer that acts as the 'entry point' for the given prim."""
    with Ar.ResolverContextBinder(prim.GetStage().GetPathResolverContext()):
        # Use Layer.Find since layer should have been open for the prim to exist.
        if layer:=Sdf.Layer.Find(Usd.ModelAPI(prim).GetAssetIdentifier().path):
            return layer
    fields = {**_get_id_fields(prim), _UNIT_UNIQUE_ID: Usd.ModelAPI(prim).GetAssetName()}
    return _find_layer_matching(fields, (i.layer for i in prim.GetPrimStack()))


def spawn_unit(parent, child, path=Sdf.Path.emptyPath):
    """Spawn a unit prim as a descendant of another.

    * Both parent and child must be existing units in the catalogue.
    * If `path <https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Path>`_ is not provided, the name of child will be used.
    * A valid `Model Hierarchy <https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-ModelHierarchy>`_ is preserved by:

      1. Turning parent into an `assembly <https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Assembly>`_.
      2. Ensuring intermediate prims between parent and child are also `models <https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Model>`_.

    * By default, spawned units are `instanceable <https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Instanceable>`_.
    """
    # TODO: spawn_many
    # this is because at the moment it is not straight forward to bring catalogue units under others.
    whole_path = Usd.ModelAPI(parent).GetAssetIdentifier().path
    target_path = UsdAsset(Path(whole_path).name).get(**{ids.CGAsset.part.name: "target"})
    parent_stage = fetch_stage(target_path, parent.GetStage().GetPathResolverContext(), Usd.Stage.LoadNone)
    origin = parent_stage.GetDefaultPrim()
    relpath = path or child.GetName()
    path = origin.GetPath().AppendPath(relpath)
    # TODO: turn into function to ensure creation and query are the same?
    child_catalogue_unit_path = _catalogue_path(child).AppendChild(Usd.ModelAPI(child).GetAssetName())
    spawned = parent_stage.DefinePrim(path)
    with Sdf.ChangeBlock():
        # Action of bringing a unit from our catalogue turns parent into an assembly only if child is a model.
        if child.IsModel():
            Usd.ModelAPI(origin).SetKind(Kind.Tokens.assembly)
            # check for all intermediate parents of our spawned unit to ensure valid model hierarchy
            for inner_parent in _usd.iprims(origin.GetStage(), [origin.GetPath()], lambda p: p == spawned.GetParent()):
                if not inner_parent.IsModel():
                    Usd.ModelAPI(inner_parent).SetKind(Kind.Tokens.group)
        # NOTE: Still experimenting to see if specializing from catalogue is a nice approach.
        # spawned.GetInherits().AddInherit(child_catalogue_unit_path)  # trumps variant selections
        # spawned.GetReferences().AddInternalReference(child_catalogue_unit_path)  # does not work
        spawned.GetSpecializes().AddSpecialize(child_catalogue_unit_path)  # does not get taxonomy values
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
    if not (fields:=prim.GetAssetInfoByKey(_ASSETINFO_FIELDS_KEY)):
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
        name = UsdAsset(Path(layer.realPath).name)
        if tokens.difference(name.values.items()):
            seen.add(layer)
            continue
        return layer
    raise ValueError(f"Could not find layer matching {tokens}. Searched on:\n{pformat(seen)}")
