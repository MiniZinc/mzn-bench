import math
from itertools import cycle

import pandas as pd
from bokeh.models import CDSView, ColumnDataSource, GroupFilter
from bokeh.models.annotations import Span
from bokeh.models.ranges import FactorRange
from bokeh.models.tools import HoverTool
from bokeh.palettes import Palette, Spectral5
from bokeh.plotting import figure, gridplot
from bokeh.transform import factor_cmap


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
