# grid-model

## Study: End of Czech coal

Welcome to the repository of source code for the model used in the publication
https://faktaoklimatu.cz/studie/2026-konec-uhli-v-cesku

The directories are structured as follows:

- `data/` contains the input data for the model from external sources, note that the data files are licensed under different terms from the rest of the repository
- `energy_insights/` contains the Python modules that make up the grid model
- `publication/figures/` contains raw SVGs of the charts that appear in the study and their underlying data in CSV
- `publication/model-runs/` contains summary statistics of the individual model runs which are used to generate some of the figures
- `sandbox/` contains notebooks and scripts to run some features of the model, notably `coal_study2_plots.ipynb` is used to generate the SVG and CSV files in the `publication/figures/` directory

## Solvers

- The default open-source solver `CBC` comes with the library `PuLP`. However, this solver is very slow.
- A slightly faster option is the open-source solver [HiGHS](https://highs.dev/) that has the python library installed through `requirements.txt`. For the solver to be available, one needs to install the executable.
  - For Fedora Linux, [an unofficial Copr repository](https://copr.fedorainfracloud.org/coprs/mgrabovs/HiGHS/) is available.
  - For other Linux distributions, [building from the source code](https://ergo-code.github.io/HiGHS/dev/interfaces/cpp/) might be required.
  - For Mac OS, `brew install highs` does the trick.
- Solid fast for our model is the commercial solver [Mosek](https://www.mosek.com/). This can be easily installed by `pip install Mosek` but one also needs to obtain a license and store it to `~/mosek/mosek.lic`. 30 days free trial license can be easily obtained at [https://www.mosek.com/try/](https://www.mosek.com/try/).
