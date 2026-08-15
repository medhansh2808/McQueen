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
        output_names=["mul_48", "linear_80", "mul_41"],
    )

    sub = onnx.load(args.out)
    print(f"extracted subgraph: {len(sub.graph.node)} nodes (down from 874), "
          f"{len(sub.graph.initializer)} initializers")
    print("Note: adding mul_41 (plan) pulls in the entire off_policy_model transformer "
          "branch — bigger than the action-only subgraph, but still far smaller than "
          "the full 874-node model since point_policy (lanes/road_edges/etc) is still cut.")
    print(f"saved -> {args.out}")
    print("\nRun convert_and_verify.py against THIS file next, not the full one —"
          " conversion + parity-checking will be much faster with a fraction of the graph.")


if __name__ == "__main__":
    main()
