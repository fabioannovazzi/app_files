import re
from io import BytesIO

import polars as pl
from modules.utilities.ui_notifier import ui
from modules.utilities.session_context import session_state

from modules.layout.layout_helpers import make_four_col_width_array
from modules.layout.memoization import get_hashed_key
from modules.utilities.config import get_naming_params
from modules.utilities.helpers import insert_json_value


def get_company_name_widget(chartDict, value, hashKey):
    namingParams = get_naming_params()
    addCompanyNameLabel = namingParams["addCompanyNameLabel"]
    datasetTypeKey = namingParams["datasetTypeName"]
    companySales = namingParams["companySales"]
    companyExpenses = namingParams["companyExpenses"]
    if chartDict[datasetTypeKey] in [companySales, companyExpenses]:
        helpMessage = "Adds company name to plot title."
        caption = """✳️Company name or company URL.
                                """
    else:
        helpMessage = "Adds market name to plot title"
        caption = """✳️Name of market.
                                """
    userInput = ui.text_input(
        label=addCompanyNameLabel,
        value=value,
        max_chars=50,
        key=hashKey,
        help=helpMessage,
        label_visibility="visible",
    )
    ui.caption(caption)
    return userInput


def extract_site_name(url):
    # Normalize the URL
    url = url.lower()

    # Remove protocol (http://, https://)
    url = re.sub(r"^https?:\/\/", "", url)

    # Remove 'www.'
    url = re.sub(r"^www\.", "", url)

    # Extract the site name by removing the domain suffix
    siteName = re.split(r"\.", url)[0]

    siteName = siteName.title()
    return siteName


def get_company_name(chartDict, automateDict, col):
    namingParams = get_naming_params()

    companyNameKey = namingParams["companyName"]
    companyUrlKey = namingParams["companyUrl"]
    hashKey = get_hashed_key(companyNameKey, companyNameKey)
    value = ""
    with col:
        value = insert_json_value(
            "input", value, automateDict, value, companyNameKey, None
        )
        userInput = get_company_name_widget(chartDict, value, hashKey)
        message = extract_site_name(userInput)
        chartDict[companyNameKey] = message
        chartDict[companyUrlKey] = userInput
    return chartDict


def convert_image_for_GPT(uploadedFile, show, RGB):
    uploadedFile = uploadedFile.getvalue()
    with Image.open(BytesIO(uploadedFile)) as image:
        if show:
            ui.image(image, caption="Uploaded Image.", width="stretch")
        image = image.convert(RGB)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        base64Image = base64.b64encode(buffer.read()).decode("utf-8")
    return base64Image


def upload_plot_image(hashKey):
    namingParams = get_naming_params()
    getChartCommentLabel = namingParams["getChartCommentLabel"]
    uploadChartLabel = namingParams["uploadChartLabel"]
    tooltip = """Upload chart to GPT."""
    message = """✳️Upload chart to GPT."""
    colArray = make_four_col_width_array()
    submitted, base64Image, fileName, disabled = False, False, False, False
    with colArray[0]:
        uploadedFile = ui.file_uploader(
            uploadChartLabel,
            type=["png"],
            key=hashKey,
            help=tooltip,
        )
        ui.caption(message)
        if uploadedFile is not None:
            fileName = uploadedFile.name
            hashKey = hashKey + getChartCommentLabel
            tooltip = """Get plot description from GPT."""
            message = """✳️Get plot description from GPT."""
            # Display the uploaded image
            base64Image = convert_image_for_GPT(uploadedFile, True, "RGB")
            submitted = ui.button(
                label=getChartCommentLabel,
                help=tooltip,
                key=hashKey,
                disabled=disabled,
                type="primary",
            )
            ui.caption(message)
    return submitted, base64Image, fileName
