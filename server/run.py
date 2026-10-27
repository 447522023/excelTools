"""开发模式启动:python run.py(需在 server/ 目录下,激活 excel_tools 环境)"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
