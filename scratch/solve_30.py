import itertools

def count_valid_arrangements():
    # 0 for Y, 1 for P, 2 for B
    items = [0]*4 + [1]*4 + [2]*4
    unique_perms = set(itertools.permutations(items))
    
    valid_count = 0
    for p in unique_perms:
        valid = True
        for i in range(len(p)-1):
            if (p[i] == 0 and p[i+1] == 1) or (p[i] == 1 and p[i+1] == 0):
                valid = False
                break
        if valid:
            valid_count += 1
            
    return valid_count

print("Total valid arrangements:", count_valid_arrangements())
