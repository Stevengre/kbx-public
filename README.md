# Introduction

This replication package includes the source code and data necessary to reproduce the results presented in the paper "KBX: Verified Model Synchronization via Formal Bidirectional Transformation".

# Structure

1. `kbx/` - Contains the source code of KBX.
2. `evaluation/` - Contains evaluation data and scripts, including:
   1. `families2persons/` - The K definition and synchronization target examples for the bidirectional transformation (BX) between Families and Persons.
   2. `hcsp2uml/` - The K definition and synchronization target examples for the BX between HCSP and PlantUML.
3. `evaluate.py` - A script to reproduce the results in the paper.
4. `prover.tar.gz` - Contains the pre-built prover for the evaluation, available for download at this [link](https://doi.org/10.5281/zenodo.7482286).

# Reproduce the Results

To reproduce the results described in the paper, execute the following commands:

1. Install the [K framework 7.1.23](https://github.com/runtimeverification/k/releases/tag/v7.1.23):
```bash
bash <(curl https://kframework.org/install)
kup install k --version v7.1.23
```

2. Prepare the Python environment using Poetry:
```bash
poetry install
poetry shell
```

3. Install `cloc` and `tokei` for counting lines of code

4. Run the evaluation script to reproduce the results:
```bash
python evaluate.py
```

# Step-by-Step Instructions to Reusing KBX
After completing Step 2, the environment for KBX is set up. To reuse KBX for verified model synchronization, follow these steps:

1. Define the K definition to specify a unidirectional transformation for the synchronization targets.
2. Use the `from kbx.generator import BXGenerator` in Python to generate a formal BX workspace:
   1. Automatically generated K definitions for BX, which you can further customize.
   2. `kbx.py` script to compile the K definitions and run the BX.
3. Generate interpreters for the synchronization using the `python kbx.py init` command. 
To generate proof hints during synchronization, add the `--allow-proof-hints` option.
4. Execute the synchronization using the `python kbx.py <direction> <source> <target>` command.
The `<direction>` can be `forward` or `backward`, and `<source>` and `<target>` are the source and target models, respectively.
To generate proof hints during synchronization, add the `--proof-hints` option.

> Our verification approach is based on the K framework, which generates proofs from these hints. 
> There are two papers that provide more details about this verification approach:
> 1. "Towards a Trustworthy Semantics-Based Language Framework via Proof Generation"
> 2. "Generating Proof Certificates for a Language-Agnostic Deductive Program Verifier"