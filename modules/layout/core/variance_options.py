from __future__ import annotations

from modules.utilities.config import get_config_params, get_naming_params

__all__ = [
    "check_if_options_compatible_with_one_dimensional",
    "select_possible_aggregation_options",
]


def select_possible_aggregation_options(param_dict: dict) -> tuple[list[str], list[str], dict]:
    """Return the variance aggregation options allowed by detected columns."""
    naming = get_naming_params()
    config = get_config_params()
    driver_cols = config[naming["driverColsArray"]]
    varianceAggregation = naming["varianceAggregation"]
    totalVarianceAggregation = naming["totalVarianceAggregation"]
    priceAndUnitsAggregation = naming["priceAndUnitsAggregation"]
    priceAndVolumeAggregation = naming["priceAndVolumeAggregation"]
    unitPriceOnSalesAggregation = naming["unitPriceOnSalesAggregation"]
    volumePriceOnSalesAggregation = naming["volumePriceOnSalesAggregation"]
    unitsOnSalesAggregation = naming["unitsOnSalesAggregation"]
    volumeOnSalesAggregation = naming["volumeOnSalesAggregation"]
    unitPriceOnMarginAggregation = naming["unitPriceOnMarginAggregation"]
    volumePriceOnMarginAggregation = naming["volumePriceOnMarginAggregation"]
    unitsOnMarginAggregation = naming["unitsOnMarginAggregation"]
    volumeOnMarginAggregation = naming["volumeOnMarginAggregation"]
    newAndLostUnitsAggregation = naming["newAndLostUnitsAggregation"]
    newAndLostVolumeAggregation = naming["newAndLostVolumeAggregation"]
    newAndLostUnitsMixAggregation = naming["newAndLostUnitsMixAggregation"]
    newAndLostVolumeMixAggregation = naming["newAndLostVolumeMixAggregation"]
    newAggregation = naming["newAggregation"]
    lostAggregation = naming["lostAggregation"]
    changedAggregation = naming["changedAggregation"]
    mixAndUnitsAggregation = naming["mixAndUnitsAggregation"]
    mixAndVolumeAggregation = naming["mixAndVolumeAggregation"]
    mixAggregation = naming["mixAggregation"]
    driverAndUnitsAggregation = naming["driverAndUnitsAggregation"]
    driverAndVolumeAggregation = naming["driverAndVolumeAggregation"]
    driverAggregation = naming["driverAggregation"]
    mixUnitsDriverAggregation = naming["mixUnitsDriverAggregation"]
    mixVolumeDriverAggregation = naming["mixVolumeDriverAggregation"]
    discountsUnitsCogsAggregation = naming["discountsUnitsCogsAggregation"]
    discountsVolumeCogsAggregation = naming["discountsVolumeCogsAggregation"]
    discountsAndUnitsAggregation = naming["discountsAndUnitsAggregation"]
    discountsAndVolumeAggregation = naming["discountsAndVolumeAggregation"]
    discountsAggregation = naming["discountsAggregation"]
    cogsAggregation = naming["cogsAggregation"]
    marginUnitsRateAggregation = naming["marginUnitsRateAggregation"]
    marginVolumeRateAggregation = naming["marginVolumeRateAggregation"]
    costsUnitsAggregation = naming["costsUnitsAggregation"]
    costsVolumeAggregation = naming["costsVolumeAggregation"]
    costsUnitsMixAggregation = naming["costsUnitsMixAggregation"]
    costsVolumeMixAggregation = naming["costsVolumeMixAggregation"]
    netOfDiscountAggregation = naming["netOfDiscountAggregation"]
    marginVarianceAggregation = naming["marginVarianceAggregation"]
    cogsColFound = naming["cogsColFound"]
    discountColFound = naming["discountColFound"]
    unitsColFound = naming["unitsColFound"]
    volumeColFound = naming["volumeColFound"]
    driverColFound = naming["driverColFound"]
    monetaryColFound = naming["monetaryLocalCurrencyColFound"]
    cwdColFound = naming["cwdColFound"]
    checkoutsColFound = naming["checkoutsColFound"]
    visitsColFound = naming["visitsColFound"]

    possibleProcessingsDict = {
        cogsColFound: [
            marginVarianceAggregation,
            marginUnitsRateAggregation,
            marginVolumeRateAggregation,
            costsUnitsAggregation,
            costsVolumeAggregation,
            costsUnitsMixAggregation,
            costsVolumeMixAggregation,
            discountsUnitsCogsAggregation,
            discountsVolumeCogsAggregation,
        ],
        discountColFound: [
            netOfDiscountAggregation,
            discountsAndUnitsAggregation,
            discountsAndVolumeAggregation,
        ],
        monetaryColFound: [totalVarianceAggregation],
        unitsColFound: [
            priceAndUnitsAggregation,
            mixAndUnitsAggregation,
            newAndLostUnitsAggregation,
            newAndLostUnitsMixAggregation,
        ],
        volumeColFound: [
            priceAndVolumeAggregation,
            mixAndVolumeAggregation,
            newAndLostVolumeAggregation,
            newAndLostVolumeMixAggregation,
        ],
        driverColFound: [
            driverAndUnitsAggregation,
            driverAndVolumeAggregation,
            mixUnitsDriverAggregation,
            mixVolumeDriverAggregation,
        ],
        cwdColFound: [
            driverAndUnitsAggregation,
            driverAndVolumeAggregation,
            mixUnitsDriverAggregation,
            mixVolumeDriverAggregation,
        ],
        checkoutsColFound: [
            driverAndUnitsAggregation,
            driverAndVolumeAggregation,
            mixUnitsDriverAggregation,
            mixVolumeDriverAggregation,
        ],
        visitsColFound: [
            driverAndUnitsAggregation,
            driverAndVolumeAggregation,
            mixUnitsDriverAggregation,
            mixVolumeDriverAggregation,
        ],
    }

    requireUnitsColumnArray = [
        discountsUnitsCogsAggregation,
        discountsAndUnitsAggregation,
        marginUnitsRateAggregation,
        costsUnitsMixAggregation,
        costsUnitsAggregation,
        priceAndUnitsAggregation,
        unitPriceOnSalesAggregation,
        unitPriceOnMarginAggregation,
        mixAndUnitsAggregation,
        mixUnitsDriverAggregation,
        driverAndUnitsAggregation,
        newAndLostUnitsAggregation,
    ]

    requireVolumeColumnArray = [
        discountsVolumeCogsAggregation,
        discountsAndVolumeAggregation,
        marginVolumeRateAggregation,
        costsVolumeMixAggregation,
        costsVolumeAggregation,
        priceAndVolumeAggregation,
        volumePriceOnSalesAggregation,
        volumePriceOnMarginAggregation,
        mixAndVolumeAggregation,
        mixVolumeDriverAggregation,
        driverAndVolumeAggregation,
        newAndLostVolumeAggregation,
    ]

    showUnitsAndVolumeColumnArray = [
        costsVolumeMixAggregation,
        mixAndVolumeAggregation,
        mixVolumeDriverAggregation,
    ]

    percentAggregationsArray = [marginVarianceAggregation]

    expandedChoiceDict = {
        marginVarianceAggregation: [],
        marginUnitsRateAggregation: [],
        costsUnitsAggregation: [],
        costsUnitsMixAggregation: [],
        discountsUnitsCogsAggregation: [
            cogsAggregation,
            discountsAggregation,
            unitPriceOnMarginAggregation,
            volumePriceOnMarginAggregation,
            unitsOnMarginAggregation,
            volumeOnMarginAggregation,
        ],
        netOfDiscountAggregation: [],
        discountsAndUnitsAggregation: [],
        totalVarianceAggregation: [],
        newAndLostUnitsMixAggregation: [
            changedAggregation,
            unitPriceOnSalesAggregation,
            newAggregation,
            lostAggregation,
            mixAggregation,
        ],
        newAndLostUnitsAggregation: [
            changedAggregation,
            unitPriceOnSalesAggregation,
            newAggregation,
            lostAggregation,
            mixAggregation,
        ],
        priceAndUnitsAggregation: [
            unitsOnSalesAggregation,
            unitPriceOnSalesAggregation,
        ],
        mixAndUnitsAggregation: [mixAggregation],
        driverAndUnitsAggregation: [driverAggregation],
        mixUnitsDriverAggregation: [driverAggregation, mixAggregation],
    }

    varianceAggregationOptions: list[str] = []
    for foundCol in possibleProcessingsDict:
        if param_dict.get(foundCol):
            for okOption in possibleProcessingsDict[foundCol]:
                if okOption not in varianceAggregationOptions:
                    varianceAggregationOptions.append(okOption)

    checkedOptions: list[str] = []
    if not param_dict.get(unitsColFound):
        for element in varianceAggregationOptions:
            if element not in requireUnitsColumnArray and element not in checkedOptions:
                checkedOptions.append(element)
        return checkedOptions, percentAggregationsArray, expandedChoiceDict
    elif not param_dict.get(volumeColFound):
        for element in varianceAggregationOptions:
            if (
                element not in requireVolumeColumnArray
                and element not in checkedOptions
            ):
                checkedOptions.append(element)
        return checkedOptions, percentAggregationsArray, expandedChoiceDict
    elif param_dict.get(unitsColFound) and param_dict.get(volumeColFound):
        for element in varianceAggregationOptions:
            if element not in checkedOptions:
                checkedOptions.append(element)
        return checkedOptions, percentAggregationsArray, expandedChoiceDict
    else:
        for element in varianceAggregationOptions:
            if (
                element not in requireVolumeColumnArray
                or element in showUnitsAndVolumeColumnArray
            ):
                checkedOptions.append(element)
        return checkedOptions, percentAggregationsArray, expandedChoiceDict


def check_if_options_compatible_with_one_dimensional(
    options: list[str], chart_dict: dict
) -> list[str]:
    """Filter variance options for one-dimensional analysis."""
    naming = get_naming_params()
    processing_choice = naming["processingChoice"]
    run_one_dimensional = naming["runOneDimensionalAnalysis"]

    if chart_dict.get(processing_choice) in [run_one_dimensional]:
        return [opt for opt in options]
    return options
