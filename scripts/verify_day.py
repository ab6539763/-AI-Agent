"""
每日交付物自动化校验脚本
功能：
1. 执行指定天数的 Jupyter Notebook (.ipynb)，并将真实运行结果回写到 cell outputs 中。
2. 运行对应 project_iterations/day_XX/tests 下的 pytest 单元测试。
"""
import argparse
import subprocess
import sys
from pathlib import Path

import nbformat
from jupyter_client.manager import KernelManager


def execute_notebook(nb_path: Path) -> None:
    """使用真实 Python 内核从头到尾执行 Notebook 并保存输出。"""
    print(f"[1/2] 正在执行 Notebook: {nb_path}")
    nb = nbformat.read(nb_path, as_version=4)

    km = KernelManager(kernel_name="python3")
    km.start_kernel()
    kc = km.client()
    kc.start_channels()
    kc.wait_for_ready(timeout=30)

    try:
        exec_count = 1
        for idx, cell in enumerate(nb.cells):
            if cell.cell_type != "code":
                continue
            source = cell.source.strip()
            if not source:
                continue

            cell.outputs = []
            cell.execution_count = exec_count
            exec_count += 1

            msg_id = kc.execute(source)
            while True:
                msg = kc.get_iopub_msg(timeout=30)
                msg_type = msg["header"]["msg_type"]
                content = msg["content"]

                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue

                if msg_type == "stream":
                    cell.outputs.append(
                        nbformat.v4.new_output(
                            output_type="stream",
                            name=content["name"],
                            text=content["text"],
                        )
                    )
                elif msg_type == "execute_result":
                    cell.outputs.append(
                        nbformat.v4.new_output(
                            output_type="execute_result",
                            data=content["data"],
                            metadata=content.get("metadata", {}),
                            execution_count=content["execution_count"],
                        )
                    )
                elif msg_type == "error":
                    cell.outputs.append(
                        nbformat.v4.new_output(
                            output_type="error",
                            ename=content["ename"],
                            evalue=content["evalue"],
                            traceback=content["traceback"],
                        )
                    )
                    raise RuntimeError(
                        f"Notebook {nb_path} Cell #{idx} 执行报错: {content['ename']}: {content['evalue']}"
                    )
                elif msg_type == "status" and content["execution_state"] == "idle":
                    break
    finally:
        kc.stop_channels()
        km.shutdown_kernel(now=True)

    nbformat.write(nb, nb_path)
    print(f"      Notebook 执行成功并已保存真实输出！")


def run_pytest(iter_dir: Path) -> None:
    """运行当日迭代版本的 pytest 单元测试。"""
    tests_dir = iter_dir / "tests"
    print(f"[2/2] 正在运行单元测试: {tests_dir}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests_dir), "-v"],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"单元测试失败: {tests_dir}")
    print("      单元测试 100% 通过！")


def main() -> None:
    parser = argparse.ArgumentParser(description="校验指定天数的 Notebook 与迭代代码")
    parser.add_argument("--nb", type=Path, required=True, help="Notebook 文件路径")
    parser.add_argument("--iter", type=Path, required=True, help="迭代目录路径")
    args = parser.parse_args()

    execute_notebook(args.nb)
    run_pytest(args.iter)


if __name__ == "__main__":
    main()
