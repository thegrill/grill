from pyscript.js_modules import code

from pprint import pp
stage = code.stage
print(f"{stage=}")
pp(dir(stage))
layer = stage.GetRootLayer()
print(f"{layer=}")
pp(dir(layer))
prim = stage.DefinePrim("/hello/world", "Xform")
print(f"prim created {prim}")
prim2 = stage.DefinePrim("/hello/source", "Sphere")
print(f"prim collected {prim2}")
pp(dir(prim))

def log(path):
    print(path)
    spec = layer.GetPrimAtPath(path)
    print(dir(spec))
    print(type(spec))

layer.Traverse("/", log)



