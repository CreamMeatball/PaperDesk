"""One PDF per process. Model memory is released when this process exits."""
import argparse
import json
import os
from pathlib import Path

VERSION = "2.142.1"
MODEL_REVISION = "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("models", type=Path)
    args = parser.parse_args()
    phase = args.output.with_suffix(".status.json")
    phase.write_text('{"state":"preparing"}', encoding="utf-8")
    os.environ.update(HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false",
                      OMP_NUM_THREADS="4", HF_HOME=str(args.models))
    snapshot = args.models / "hub/models--docling-project--docling-layout-heron/snapshots" / MODEL_REVISION
    if all((snapshot / name).is_file() for name in ("config.json", "preprocessor_config.json", "model.safetensors")):
        os.environ["HF_HUB_OFFLINE"] = "1"
    from importlib.metadata import version
    if version("docling-slim") != VERSION:
        raise RuntimeError("Unsupported Docling version")
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    options = PdfPipelineOptions(do_ocr=False, do_table_structure=False, do_formula_enrichment=False,
                                 enable_remote_services=False,
                                 accelerator_options=AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU))
    options.layout_options.model_spec.revision = MODEL_REVISION
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    converter.initialize_pipeline(InputFormat.PDF)
    phase.write_text('{"state":"running"}', encoding="utf-8")
    result = converter.convert(args.source)
    if result.status.value != "success":
        raise RuntimeError("Incomplete PDF analysis")
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps({"engine": "docling", "version": VERSION,
                                     "document": result.document.export_to_dict()}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
