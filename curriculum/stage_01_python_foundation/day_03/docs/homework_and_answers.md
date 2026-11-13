# Day 03 课后作业与参考答案

## 作业一：实战逻辑题（猜数字游戏逻辑 —— `while` 循环与条件分支）
**题目**：在测试智能体容错率时，我们常需要编写带重试上限的交互循环。请实现一个猜数字游戏函数 `guess_number_game(secret: int, guesses: list[int], max_attempts: int = 5) -> str`（用列表模拟玩家每次输入的猜测数字，便于单元测试）：
1. 使用循环逐个读取 `guesses` 中的猜测数字，最多允许尝试 `max_attempts` 次。
2. 每次比较猜测值 `guess` 与目标值 `secret`：
   - 若相等，返回 `"恭喜猜中！共用了 X 次。"`；
   - 若 `guess > secret`，记录提示 `"太大了"`；
   - 若 `guess < secret`，记录提示 `"太小了"`。
3. 若超过 `max_attempts` 次仍未猜中（或列表耗尽），返回 `"挑战失败，正确答案是 {secret}。"`。

### 参考答案：
```python
def guess_number_game(
    secret: int,
    guesses: list[int],
    max_attempts: int = 5,
) -> str:
    """模拟带最大尝试次数限制的猜数字游戏逻辑。"""
    attempt = 0
    while attempt < max_attempts and attempt < len(guesses):
        guess = guesses[attempt]
        attempt += 1

        if guess == secret:
            return f"恭喜猜中！共用了 {attempt} 次。"
        elif guess > secret:
            print(f"第 {attempt} 次 ({guess}): 太大了")
        else:
            print(f"第 {attempt} 次 ({guess}): 太小了")

    return f"挑战失败，正确答案是 {secret}。"


# 示例验证
print(guess_number_game(42, [20, 60, 42]))
```

---

## 作业二：嵌套循环经典题（9×9 乘法口诀表）
**题目**：请使用嵌套 `for` 循环编写程序，在终端打印标准的 `9×9` 下三角乘法口诀表，要求每一行对齐整洁，且不额外引入第三方库。

### 参考答案：
```python
def print_9x9_table() -> None:
    """使用双层 for 循环打印标准 9x9 乘法口诀表。"""
    for i in range(1, 10):          # 外层循环控制行号（1 到 9）
        row_items = []
        for j in range(1, i + 1):   # 内层循环控制列号（1 到 i）
            row_items.append(f"{j}×{i}={i * j:<2}")
        print("  ".join(row_items))


print_9x9_table()
```

---

## 作业三：算法思维冲刺（2 道 LeetCode-Easy 经典题）
**题目 A（LeetCode #1 两数之和 Two Sum）**：
给定一个整数列表 `nums` 和一个整数目标值 `target`，请你在该数组中找出和为目标值 `target` 的那两个整数，并返回它们的数组下标（假设每种输入只会对应一个答案，且不能重复利用同一个元素）。

**题目 B（LeetCode #9 回文数 Palindrome Number）**：
给你一个整数 `x`，如果 `x` 是一个回文整数（正序和倒序读都一样，如 `121`），返回 `True`；否则返回 `False`（注意负数如 `-121` 不是回文数）。

### 参考答案：
```python
# 题目 A：两数之和（使用循环 + 字典/哈希表优化至 O(n)）
def two_sum(nums: list[int], target: int) -> list[int]:
    seen: dict[int, int] = {}  # 记录 {数值: 下标}
    for idx, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], idx]
        seen[num] = idx
    return []


# 题目 B：回文数（不使用字符串转换，纯 while 循环反转一半数字）
def is_palindrome(x: int) -> bool:
    # 负数以及末尾为 0 且不为 0 本身的数，不可能是回文数
    if x < 0 or (x % 10 == 0 and x != 0):
        return False

    reversed_half = 0
    while x > reversed_half:
        reversed_half = reversed_half * 10 + x % 10
        x //= 10

    # 当数字长度为奇数时，可通过 reversed_half // 10 去除中间位
    return x == reversed_half or x == reversed_half // 10


print("Two Sum:", two_sum([2, 7, 11, 15], 9))       # [0, 1]
print("Palindrome 121:", is_palindrome(121))        # True
print("Palindrome -121:", is_palindrome(-121))      # False
```
