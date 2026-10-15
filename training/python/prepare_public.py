"""Prepare only pinned, observed public datasets; never merge legacy seeds."""
from public_sources import ADAPTERS, build_public_dataset

if __name__ == "__main__":
    for model in ADAPTERS:
        frame, _ = build_public_dataset(model)
        print(f"{model}: {len(frame)} public observations, {frame['group_key'].nunique()} independent groups")
