def count_arrangements(y_left, p_left, b_left, last_color):
    if y_left == 0 and p_left == 0 and b_left == 0:
        return 1
    
    ways = 0
    # Add Y
    if y_left > 0 and last_color != 'P':
        ways += count_arrangements(y_left - 1, p_left, b_left, 'Y')
    
    # Add P
    if p_left > 0 and last_color != 'Y':
        ways += count_arrangements(y_left, p_left - 1, b_left, 'P')
        
    # Add B
    if b_left > 0:
        ways += count_arrangements(y_left, p_left, b_left - 1, 'B')
        
    return ways

print("Recursive count:", count_arrangements(4, 4, 4, ''))
