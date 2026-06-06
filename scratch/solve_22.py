import sys

memo = {}

def get_a(k):
    if k in memo: return memo[k]
    if k == 1: return 1
    if k == 2: return 2
    if k == 3: return 4
    
    if k % 2 == 0:
        res = get_a(k // 2) + 1
    elif k % 4 == 1:
        n = (k - 1) // 4
        res = get_a(n) + 4
    elif k % 4 == 3:
        n = (k - 3) // 4
        res = get_a(n) + 4
    else:
        raise ValueError("Impossible")
    
    memo[k] = res
    return res

# How large can k be?
# Max increase is +4 for *4.
# k ~ 4^(10/4) ~ 4^2.5 ~ 32... No, a_k grows at least by 1 for *2, so max k is 2^10 = 1024.
# Actually, +4 for *4 is same as +1 for *2 roughly.
# Wait, a_n+4 for 4n+1 means a_k ~ log2(k). So for a_k=10, k ~ 2^10 = 1024.
# But wait, +4 for *4 is very fast growth in value.
# So k could be small? No, +1 for *2 means a_1024 = 11.
# +4 for *4 means a_1 = 1, a_5 = 5, a_21 = 9.
# Let's just generate up to a large number. Wait!
# 10 is very small. Let's just iterate up to 100,000.
count = 0
# Actually, to be safe, compute up to 1,000,000.
for i in range(1, 1000000):
    if get_a(i) == 10:
        count += 1
print("Count:", count)

# Let's also print max value in 1,000,000
m = max(get_a(i) for i in range(1, 1000000))
print("Max value up to 1M:", m)

