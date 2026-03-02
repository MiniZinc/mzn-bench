import math
from itertools import cycle
from typing import Mapping, Sequence

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from bokeh.models import CDSView, ColumnDataSource, GroupFilter
from bokeh.models.annotations import Span
from bokeh.models.ranges import FactorRange
from bokeh.models.tools import HoverTool
from bokeh.palettes import Palette, Spectral5
from bokeh.plotting import figure, gridplot
from bokeh.transform import factor_cmap


def plot_cactus(stats: pd.DataFrame):
    configurations = stats["configuration"].unique()

    frames = []
    for conf in configurations:
        # Filter statistics to find completed instances
        conf_stats = stats[
            (stats["configuration"] == conf)
            & (
                (stats["status"] == "OPTIMAL_SOLUTION")
                | ((stats["status"] == "SATISFIED") & (stats["method"] == "satisfy"))
            )
        ]

        # Extract solving time and sort in ascending order
        t = pd.DataFrame({"time": sorted(conf_stats["time"])})

        # Add the position in the column (i.e. 1..n) as the number of instances
        # solved in up to the time in that row
        t["n_solved"] = list(range(1, 1 + len(t)))

        # Label with the associated configuration
        t["configuration"] = conf
        frames.append(t)

    data = pd.concat(frames, ignore_index=True)

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.lineplot(
        ax=ax,
        data=data,
        y="time",
        x="n_solved",
        hue="configuration",
        style="configuration",
        markers=True,
        dashes=False,
    )
    ax.set(
        title="Comparison of solved instances between different configurations",
        ylabel="CPU time(seconds)",
        xlabel="# of instances solved",
    )
    sns.move_legend(ax, "upper left", bbox_to_anchor=(1.01, 1), borderaxespad=0)
    fig.tight_layout()

    return fig


def plot_all_instances(
    sols: pd.DataFrame, stats: pd.DataFrame, palette: Palette = Spectral5
) -> figure:
    """Plot all instances in a grid

    Args:
        sols (pd.DataFrame): The solution data frame
        stats (pd.DataFrame): The statistics data frame
        palette (Palette, optional): The colour palette to use. Defaults to Spectral5.

    Returns:
        figure: The plotting figure
    """
    return gridplot(
        [
            [
                plot_instance(
                    sols,
                    stats,
                    model,
                    data,
                    palette,
                )
                for model in stats[stats.problem.eq(problem)].model.unique()
                for data in stats[stats.problem.eq(problem)].data_file.unique()
            ]
            for problem in stats.problem.unique()
        ]
    )


def plot_instance(
    sols: pd.DataFrame,
    stats: pd.DataFrame,
    model: str,
    data: str = "",
    palette: Palette = Spectral5,
) -> figure:
    """Plots objective data for an optimisation problem instance, and run time
       data for a satisfaction problem instance.

    Args:
        sols (pd.DataFrame): The solution data frame
        stats (pd.DataFrame): The statistics data frame
        model (str): The model file path or problem name of the instance
        data (str, optional): The data file path or name. Defaults to "".
        palette (Palette, optional): The colour palette to use. Defaults to Spectral5.

    Returns:
        figure.Figure: The plotting figure
    """
    df_stats = stats[
        (stats.model.eq(model) | stats.problem.eq(model)) & stats.data_file.eq(data)
    ]
    df_sols = sols[
        (sols.model.eq(model) | sols.problem.eq(model)) & sols.data_file.eq(data)
    ]
    if df_stats.data_file.nunique() != 1:
        print(stats[stats.model.eq(model)])
        raise ValueError("Could not determine unique instance for plotting.")

    instance = "{} ({})".format(
        df_stats.problem.iloc[0],
        df_stats.model.iloc[0]
        if df_stats.data_file.iloc[0] == ""
        else df_stats.data_file.iloc[0],
    )

    if df_stats.method.eq("satisfy").any() or df_sols.empty:
        # Plot run time graph
        if df_stats.configuration.nunique() == 1:
            # Group by run only
            y = df_stats.run.unique()
            by = ["run"]
        elif df_stats.run.nunique() == 1:
            # Group by configuration only
            y = df_stats.configuration.unique()
            by = ["configuration"]
        else:
            # Group by both
            y = [
                (c, r)
                for c in df_stats.configuration.unique()
                for r in df_stats.run.unique()
            ]
            by = ["configuration", "run"]

        tooltips = [
            ("configuration", "@" + "_".join(by)),
            ("flatTime", "@flatTime"),
            ("solveTime", "@solveTime"),
            ("time", "@time"),
            ("status", "@status"),
        ]
        source = ColumnDataSource(df_stats.groupby(by=by).first())
        p = figure(
            y_range=FactorRange(*y),
            title="Run time for {}".format(instance),
            tooltips=tooltips,
        )
        p.hbar(
            y="_".join(by),
            left="flatTime",
            right="time",
            height=0.5,
            fill_color=factor_cmap(
                "_".join(by),
                palette=palette,
                factors=df_stats[by[-1]].unique(),
                start=len(by) - 1,
            ),
            line_color=None,
            source=source,
        )
        p.x_range.start = 0
        p.xaxis.axis_label = "Time (s)"
        p.yaxis.axis_label = "Configuration"
        return p
    else:
        # Plot objective graph
        source = ColumnDataSource(df_sols)
        tooltips = [
            ("configuration", "@configuration"),
            ("run", "@run"),
            ("time", "@time"),
            ("objective", "@objective"),
        ]

        p = figure(title="Objective value for {}".format(instance))
        colors = cycle(palette)
        for configuration in df_stats.configuration.unique():
            color = next(colors)
            dashes = cycle([[], [6], [2, 4], [2, 4, 6, 4], [6, 4, 2, 4]])
            for run, line_dash in zip(df_stats.run.unique(), dashes):
                view = CDSView(
                    source=source,
                    filters=[
                        GroupFilter(column_name="configuration", group=configuration),
                        GroupFilter(column_name="run", group=run),
                    ],
                )
                glyph = p.circle(
                    x="time",
                    y="objective",
                    color=color,
                    legend_label=", ".join([configuration, run]),
                    source=source,
                    view=view,
                )
                p.add_tools(HoverTool(renderers=[glyph], tooltips=tooltips))
                p.step(
                    x="time",
                    y="objective",
                    mode="after",
                    color=color,
                    line_dash=line_dash,
                    legend_label=", ".join([configuration, run]),
                    source=source,
                    view=view,
                )

                # Add markers for flatTime and time stats
                y_pos = df_sols.objective.median()
                if math.isnan(y_pos):
                    y_pos = 0
                stats = df_stats[
                    df_stats.configuration.eq(configuration) & df_stats.run.eq(run)
                ].iloc[0]
                start = Span(
                    location=stats.flatTime,
                    dimension="height",
                    line_alpha=0.5,
                    line_color=color,
                    line_dash=line_dash,
                )
                p.add_layout(start)
                end = Span(
                    location=stats.time,
                    dimension="height",
                    line_alpha=0.5,
                    line_color=color,
                    line_dash=line_dash,
                )
                p.add_layout(end)
                glyph = p.circle([stats.flatTime], [y_pos], fill_alpha=0, line_alpha=0)
                p.add_tools(
                    HoverTool(
                        renderers=[glyph],
                        tooltips=[
                            ("configuration", configuration),
                            ("run", run),
                            ("flatTime", str(stats.flatTime)),
                        ],
                        mode="vline",
                        point_policy="follow_mouse",
                    )
                )
                glyph = p.circle([stats.time], [y_pos], fill_alpha=0, line_alpha=0)
                end_tooltips = [
                    ("configuration", configuration),
                    ("run", run),
                    ("time", str(stats.time)),
                    ("status", str(stats.status)),
                ]
                if stats.status in ["SATISFIED", "OPTIMAL_SOLUTION"]:
                    end_tooltips.append(["objective", str(stats.objective)])
                p.add_tools(
                    HoverTool(
                        renderers=[glyph],
                        tooltips=end_tooltips,
                        mode="vline",
                        point_policy="follow_mouse",
                    )
                )
        p.x_range.start = 0
        p.x_range.end = df_stats.time.max()
        p.xaxis.axis_label = "Time (s)"
        p.yaxis.axis_label = "Objective"
        p.legend.click_policy = "hide"
        return p


def plot_total_time(stats: pd.DataFrame, palette: Palette = Spectral5) -> figure:
    """Plots a summary bar graph giving total run time for each configuration
        and run.

    Args:
        stats (pd.DataFrame): Data frame containing the statistics output
        palette (Palette, optional): Colour palette. Defaults to Spectral5.

    Returns:
        figure: The plotting figure
    """

    if stats.configuration.nunique() == 1:
        # Group by run only
        y = stats.run.unique()
        by = ["run"]
    elif stats.run.nunique() == 1:
        # Group by configuration only
        y = stats.configuration.unique()
        by = ["configuration"]
    else:
        # Group by both
        y = [(c, r) for c in stats.configuration.unique() for r in stats.run.unique()]
        by = ["configuration", "run"]
    df = stats.groupby(by=by).sum()
    tooltips = [
        ("configuration", "@" + "_".join(by)),
        ("time", "@time"),
    ]
    p = figure(
        y_range=FactorRange(*y),
        title="Total run time for all instances",
        tooltips=tooltips,
    )
    p.hbar(
        y="_".join(by),
        right="time",
        height=0.5,
        fill_color=factor_cmap(
            "_".join(by),
            palette=palette,
            factors=stats.run.unique() if len(by) > 1 else y,
            start=len(by) - 1,
        ),
        line_color=None,
        source=ColumnDataSource(df),
    )
    p.x_range.start = 0
    p.xaxis.axis_label = "Time (s)"
    p.yaxis.axis_label = "Configuration"
    return p


def plot_primal_integral(
    solns: pd.DataFrame,
    par: int = 2,
    palette: Palette = Spectral5,
    title: str = "Summed objective over time",
    x_label: str = "Time (s)",
    y_label: str = "Objective",
    log_y: bool = False,
    show_legend: bool = True,
    configuration_order: Sequence[str] | None = None,
    rename_configurations: Mapping[str, str] | None = None,
) -> figure:
    """Plots a summary bar graph giving primal integral for each configuration
        and run.

    Args:
        solns (pd.DataFrame): Data frame containing the solutions output
        par (int, optional): Penalty factor applied while no solution has been achieved for instance (N times worst objective score). Defaults to 2.
        palette (Palette, optional): Colour palette. Defaults to Spectral5.
        title (str, optional): Plot title.
        x_label (str, optional): X axis label.
        y_label (str, optional): Y axis label.
        log_y (bool, optional): Whether to use a logarithmic y-axis.
        show_legend (bool, optional): Whether to show a legend.
        configuration_order (Sequence[str] | None, optional):
            Preferred order for plotting configurations.
        rename_configurations (Mapping[str, str] | None, optional):
            Mapping from configuration name to display name.

    Returns:
        figure: The plotting figure
    """
    required = {
        "configuration",
        "problem",
        "model",
        "data_file",
        "time",
        "run",
        "objective",
    }
    missing = required.difference(solns.columns)
    if missing:
        raise ValueError(
            "Missing required columns for primal integral plot: {}".format(
                ", ".join(sorted(missing))
            )
        )

    df = solns.copy()
    df["data_file"] = df["data_file"].fillna("")
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df["objective"] = pd.to_numeric(df["objective"], errors="coerce")
    df = df.dropna(subset=["time", "objective"])
    # Reduce noise from dense timestamps by binning solutions to nearest second.
    df["time"] = df["time"].round().astype(int)

    instance_cols = ["model", "data_file"]
    times = sorted(df["time"].unique())
    max_time = max(times)
    if 0.0 not in times:
        times = [0.0] + times
    if times[-1] != max_time:
        times.append(max_time)

    worst_by_instance = df.groupby(instance_cols)["objective"].max()
    penalty_by_instance = worst_by_instance * par
    configurations = list(df["configuration"].unique())
    if configuration_order is not None:
        ordered = [conf for conf in configuration_order if conf in configurations]
        remaining = [conf for conf in configurations if conf not in ordered]
        configurations = ordered + remaining

    rows = []
    for configuration in configurations:
        conf = df[df["configuration"].eq(configuration)]
        for instance in penalty_by_instance.index:
            instance_mask = conf["model"].eq(instance[0]) & conf["data_file"].eq(
                instance[1]
            )
            series = (
                conf[instance_mask]
                .sort_values("time")[["time", "objective"]]
                .groupby("time", as_index=False)
                .min()
            )
            series["objective"] = series["objective"].cummin()
            idx = 0
            current = penalty_by_instance.loc[instance]
            for t in times:
                while idx < len(series) and series.iloc[idx]["time"] <= t:
                    current = series.iloc[idx]["objective"]
                    idx += 1
                rows.append(
                    {
                        "configuration": configuration,
                        "time": t,
                        "objective": current,
                    }
                )

    plot_df = (
        pd.DataFrame(rows)
        .groupby(["configuration", "time"], as_index=False)["objective"]
        .sum()
        .sort_values(["configuration", "time"])
    )

    rename_configurations = (
        {} if rename_configurations is None else dict(rename_configurations)
    )

    fig, ax = plt.subplots(figsize=(12, 5))
    colors = cycle(palette)
    for configuration, color in zip(configurations, colors):
        conf_df = plot_df[plot_df["configuration"].eq(configuration)]
        ax.step(
            conf_df["time"],
            conf_df["objective"],
            where="post",
            label=rename_configurations.get(configuration, configuration),
            color=color,
        )

    ax.set(
        title=title,
        xlabel=x_label,
        ylabel=y_label,
    )
    if log_y:
        if (plot_df["objective"] <= 0).any():
            raise ValueError(
                "Cannot use logarithmic y-axis with non-positive objective values."
            )
        ax.set_yscale("log")
    if show_legend:
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), borderaxespad=0)
    fig.tight_layout()
    return fig
