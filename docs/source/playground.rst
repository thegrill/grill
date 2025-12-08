Playground
----------

.. raw:: html

    <div id="viewer-container"></div>

    <script type="importmap">
    {
        "imports": {
            "@rerun-io/web-viewer": "https://esm.sh/@rerun-io/web-viewer@0.27.2"
        }
    }
    </script>

    <script type="module">
        import { WebViewer } from "@rerun-io/web-viewer";

        const rrdUrl = "https://app.rerun.io/version/0.27.2/examples/dna.rrd";
        const parentElement = document.getElementById("viewer-container");
        const viewer = new WebViewer();

        await viewer.start(rrdUrl, parentElement, {width: "100%", height: "100%"});
    </script>
