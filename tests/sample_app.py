from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


class NewItem(BaseModel):
    name: str


def make_app(lifespan=None) -> FastAPI:
    app = FastAPI(title="Sample API", lifespan=lifespan)
    items = {1: {"id": 1, "name": "apple"}}

    @app.get("/items", summary="List items")
    def list_items():
        return list(items.values())

    @app.get("/items/{item_id}", summary="Get an item by id")
    def get_item(item_id: int):
        if item_id not in items:
            raise HTTPException(status_code=404, detail="item not found")
        return items[item_id]

    @app.post("/items", summary="Create an item")
    def create_item(item: NewItem):
        new_id = max(items) + 1
        items[new_id] = {"id": new_id, "name": item.name}
        return items[new_id]

    @app.post("/items/{item_id}/star", summary="Star an item", openapi_extra={"x-mcp": True})
    def star_item(item_id: int):
        return {"starred": item_id}

    @app.get("/me", summary="Return the authenticated user")
    def me(authorization: str | None = Header(default=None)):
        if authorization != "Bearer good-token":
            raise HTTPException(status_code=401, detail="bad token")
        return {"user": "alice"}

    @app.get("/boom", summary="Always fails")
    def boom():
        raise RuntimeError("secret internal detail")

    @app.get("/admin/stats", summary="Admin statistics")
    def admin_stats():
        return {"items": len(items)}

    return app
