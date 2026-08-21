import argparse

import onnx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--out", default="mcqueen_action_subgraph.onnx")
    args = ap.parse_args()


    onnx.utils.extract_model(
        input_path=args.onnx,
        output_path=args.out,
        input_names=["img", "big_img", "desire_pulse", "traffic_convention", "action_t", "features_buffer"],
        output_names=["outputs"],
    )

    sub = onnx.load(args.out)
    print(f"extracted subgraph: {len(sub.graph.node)} nodes, "
          f"{len(sub.graph.initializer)} initializers")
    print("NOTE 2026-08-17: the original mul_48/linear_80/mul_41 output names were the")
    print("previous agent's UNVERIFIED contract — no comma export ever had them (verified")
    print("against v0.8.11/v0.8.16-era/v0.9.4/2026-master exports: all are new-API, and the")
    print("2026 master driving_supercombo has NO action head; control is plan-derived).")
    print("This extraction is now an identity re-export: same 6 inputs in, single 'outputs'")
    print("tensor out — the pipeline uses the FULL model via action_adapter.FrozenActionModel.")
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
