from typing import Literal
from pydantic import BaseModel, Field

class ExtractDataPoint(BaseModel):
    label: str = Field( 
        description="The name or category of the extracted data point"
    )
    value: str = Field(
        description="The text or numerical value associated with the label"
    )

class VisionExtractionReport(BaseModel):
    image_description :str = Field(

    )
    extracted_data: list[ExtractDataPoint] = Field(
        description = "Structed information extracted from the image"

    )
    confidence: Literal["High", "Medium", "Low"] = Field(
        description= "The model's confodence in the extraction"

    )
