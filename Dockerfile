FROM docker.io/jupyter/base-notebook:ubuntu-22.04

USER $NB_UID

WORKDIR $HOME/work/sandbox

# Install Poetry system-wide with pipx, which keeps it isolated in its own
# virtual env.
RUN python -m pip install --no-cache-dir pipx && \
    pipx ensurepath && \
    pipx install poetry
ENV PATH="${HOME}/.local/bin:${PATH}"

COPY --chown=${NB_UID}:${NB_UID} data/ $HOME/work/data/
COPY --chown=${NB_UID}:${NB_UID} energy_insights/ $HOME/work/energy_insights/
COPY --chown=${NB_UID}:${NB_UID} sandbox/ $HOME/work/sandbox/
COPY --chown=${NB_UID}:${NB_UID} pyproject.toml $HOME/work/

# Resolve and install dependencies and build a wheel of the project. We don't
# need Poetry in the runtime stage. The wheel will be copied over and installed
# by pip.
RUN poetry install --no-interaction --no-ansi --no-root && \
    mkdir output/

EXPOSE 8888

# Serve on localhost port 8888 and disable authentication on the server.
# TODO: Update `NotebookApp.token` to `ServerApp.token` once the former is
# deprecated.
CMD ["jupyter", "notebook", "--no-browser", "--port=8888", "--ip=0.0.0.0", "--NotebookApp.token="]
