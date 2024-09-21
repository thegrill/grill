import './emHdBindings.js';

export const usd = await globalThis["NEEDLE:USD:GET"]({
  mainScriptUrlOrBlob: "/emHdBindings.js",
  debug: true
});
console.log('loaded usd');

//export const stage = usd.UsdStage.CreateNew("test.usda");

// https://github.com/needle-tools/usd-viewer/blob/d69afccda742d46adc96f8696a92900aaf87b001/usd-wasm/README.md?plain=1#L42
const blob = await fetch("lab_inspiration01_mini.usdz");
console.log('fetched');
const arrayBuffer = await blob.arrayBuffer();
console.log('created buffer');

usd.FS_createDataFile("", "lab_inspiration01_mini.usdz", new Uint8Array(arrayBuffer), true, true, true);
console.log('created data file');
export const stage = usd.UsdStage.Open("lab_inspiration01_mini.usdz");

console.log("loaded stage")
