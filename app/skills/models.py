"""Skill data models."""

from pydantic import BaseModel


class ApiParam(BaseModel):
    name: str
    type: str = "string"       # string / number / boolean
    required: bool = False
    description: str = ""


class ApiEndpoint(BaseModel):
    name: str                   # e.g. "check_inventory"
    description: str = ""
    method: str = "GET"         # GET / POST
    path: str = ""              # e.g. "/api/v1/inventory"
    params: list[ApiParam] = []
    mock_response: dict = {}    # mock return data


class Skill(BaseModel):
    name: str                   # unique identifier
    display_name: str = ""
    description: str = ""
    category: str = "supplier"  # supplier / internal
    version: str = "1.0"
    body: str = ""              # full markdown body (after frontmatter)
    company_info: dict = {}     # parsed company info
    apis: list[ApiEndpoint] = []  # parsed API endpoints
    execution_guide: str = ""   # execution instructions section

    @property
    def summary(self) -> str:
        """One-line summary for Supervisor's skill list."""
        return f"- {self.name}: {self.description}"

    @property
    def api_names(self) -> list[str]:
        return [a.name for a in self.apis]

    def get_api(self, name: str) -> ApiEndpoint | None:
        for a in self.apis:
            if a.name == name:
                return a
        return None
