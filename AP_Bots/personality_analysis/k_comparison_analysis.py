import json
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from AP_Bots.utils.argument_parser import get_args, parse_dataset


def load_and_filter_data(file_path, k_range):
    """Load data and filter for specified conditions"""
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    included_models = {
        'LLAMA': ['LLAMA-3.1-8B', 'LLAMA-3.3-70B'],
        'GEMMA': ['GEMMA-2-9B', 'GEMMA-2-27B'],
    }
    
    filtered_data = {}
    for exp_name, exp_data in data.items():
        params = exp_data['params']
        model = params['model']
        model_family = model.split('-')[0]
        
        if (params['features'] == "" and 
            params['RS'] == '1' and 
            params['k'] in k_range and
            model_family in included_models and
            model in included_models[model_family]):
            filtered_data[exp_name] = exp_data
    
    print(filtered_data.keys())
    return filtered_data

def analyze_scores(filtered_data, k_range):
    """Analyze rouge scores for different k values and models"""
    results = {k: {} for k in k_range}
    
    for exp_name, exp_data in filtered_data.items():
        k = exp_data['params']['k']
        model = exp_data['params']['model']
        scores = np.array(exp_data['rougeL'])
        
        if k in results:
            if model not in results[k]:
                results[k][model] = []
            results[k][model].extend(scores)
    
    return results

def create_model_display_name(model):
    """Create a display name for the model"""
    family = model.split('-')[0]
    size = model.split('-')[-1]
    return f"{family}\n{size}"

def analyze_score_transitions(results, output_dir):

    stats_data = []
    bins = [-np.inf, 0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, np.inf]
    bin_labels = ['0', '0-0.05', '0.05-0.1', '0.1-0.15', '0.15-0.2', '0.2-0.25', '0.25-0.3', '>0.3']
    
    for k in results.keys():
        for model in results[k].keys():
            scores = np.array(results[k][model])
            binned_scores = pd.cut(scores, bins=bins, labels=bin_labels)
            bin_counts = binned_scores.value_counts()
            bin_percentages = (bin_counts / len(scores) * 100).round(2)
            
            # Calculate statistics
            stats = {
                'Model': model,
                'k': k,
                'Mean': np.mean(scores).round(4),
                'Median': np.median(scores).round(4),
                'Std': np.std(scores).round(4),
                'Min': np.min(scores).round(4),
                'Max': np.max(scores).round(4),
                'Zero_Count': np.sum(scores == 0),
                'Zero_Percentage': (np.sum(scores == 0) / len(scores) * 100).round(2)
            }
            
            # Add bin percentages
            for bin_label in bin_labels:
                stats[f'Bin_{bin_label}_Count'] = bin_counts.get(bin_label, 0)
                stats[f'Bin_{bin_label}_Percentage'] = bin_percentages.get(bin_label, 0)
            
            # Add quartile information
            q1, q3 = np.percentile(scores, [25, 75])
            stats.update({
                'Q1': q1.round(4),
                'Q3': q3.round(4),
                'IQR': (q3 - q1).round(4)
            })
            
            stats_data.append(stats)
    
    # Create and save comprehensive statistics DataFrame
    stats_df = pd.DataFrame(stats_data)
    stats_df = stats_df.sort_values(['Model', 'k'])
    stats_csv_path = f'{output_dir}/comprehensive_statistics.csv'
    stats_df.to_csv(stats_csv_path, index=False)
    print(f"\nSaved comprehensive statistics to: {stats_csv_path}")
    
    # Continue with transition analysis
    bins = [-np.inf, 0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, np.inf]
    bin_labels = ['0', '0-0.05', '0.05-0.1', '0.1-0.15', '0.15-0.2', '0.2-0.25', '0.25-0.3', '>0.3']
    
    # Prepare data for each model
    transition_stats = {}
    detailed_transitions = {}

    max_k = [r for r in results.keys() if r != "0"][0]
    
    for model in results['0'].keys():
        scores_k0 = np.array(results['0'][model])
        scores_maxk = np.array(results[max_k][model])
        
        # Basic statistics
        total_samples = len(scores_k0)
        improved = np.sum(scores_maxk > scores_k0)
        worsened = np.sum(scores_maxk < scores_k0)
        unchanged = np.sum(scores_maxk == scores_k0)
        
        became_zero = np.sum((scores_k0 > 0) & (scores_maxk == 0))
        zero_to_nonzero = np.sum((scores_k0 == 0) & (scores_maxk > 0))
        
        bins_k0 = pd.cut(scores_k0, bins=bins, labels=bin_labels)
        bins_maxk = pd.cut(scores_maxk, bins=bins, labels=bin_labels)
        
        # Create transition DataFrame
        transitions_df = pd.DataFrame({
            'k0_bin': bins_k0,
            'kmax_bin': bins_maxk,
            'k0_score': scores_k0,
            'kmax_score': scores_maxk
        })
        
        # Calculate mean score change for each starting bin
        transition_summary = []
        for start_bin in bin_labels:
            bin_data = transitions_df[transitions_df['k0_bin'] == start_bin]
            if len(bin_data) > 0:
                # Calculate where scores moved to
                dest_counts = bin_data['kmax_bin'].value_counts()
                total_in_bin = len(bin_data)
                
                # Calculate mean score change
                mean_score_change = (bin_data['kmax_score'] - bin_data['k0_score']).mean()
                
                # Get top 3 destinations
                top_destinations = dest_counts.nlargest(3)
                dest_str = ' | '.join([f"{idx}: {val/total_in_bin*100:.1f}%" 
                                     for idx, val in top_destinations.items()])
                
                transition_summary.append({
                    'Start Bin': start_bin,
                    'Count': total_in_bin,
                    'Mean Score Change': mean_score_change,
                    'Top Destinations': dest_str
                })
        
        detailed_transitions[model] = pd.DataFrame(transition_summary)
        
        # Store basic statistics
        transition_stats[model] = {
            'improved': improved / total_samples * 100,
            'worsened': worsened / total_samples * 100,
            'unchanged': unchanged / total_samples * 100,
            'became_zero': became_zero,
            'became_zero_pct': became_zero / total_samples * 100,
            'zero_to_nonzero': zero_to_nonzero,
            'zero_to_nonzero_pct': zero_to_nonzero / total_samples * 100,
            'total_samples': total_samples
        }
    
    # Print transition statistics and detailed transitions
    print(f"\nScore Transition Analysis (k=0 → k={max_k}):")
    for model in transition_stats.keys():
        stats = transition_stats[model]
        print(f"\n{model}:")
        print(f"  Total samples: {stats['total_samples']}")
        print(f"  Improved scores: {stats['improved']:.1f}%")
        print(f"  Worsened scores: {stats['worsened']:.1f}%")
        print(f"  Unchanged scores: {stats['unchanged']:.1f}%")
        print(f"  Non-zero → Zero: {stats['became_zero']} samples ({stats['became_zero_pct']:.1f}%)")
        print(f"  Zero → Non-zero: {stats['zero_to_nonzero']} samples ({stats['zero_to_nonzero_pct']:.1f}%)")
        
        print(f"\nDetailed Transitions for {model}:")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        print(detailed_transitions[model].to_string(index=False))
        print("\n" + "="*80)
        
        # Save the transition DataFrame to CSV
        csv_filename = f'{output_dir}/transitions_{model.replace("-", "_").lower()}.csv'
        detailed_transitions[model].to_csv(csv_filename, index=False)
        print(f"Saved transition details to: {csv_filename}")

def plot_comparisons(results, output_dir, k_range):
    """Create plots comparing all models"""    

    plot_data = []
    for k in sorted(results.keys()):
        for model in sorted(results[k].keys()):
            scores = results[k][model]
            display_name = create_model_display_name(model)
            plot_data.extend([(score, k, display_name) for score in scores])
    
    df = pd.DataFrame(plot_data, columns=['score', 'k', 'model'])
    df['k'] = pd.Categorical(df['k'], categories=k_range, ordered=True)
    
    # Set style
    sns.set_style("whitegrid")
    
    # Box plot for all models
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=df, x='model', y='score', hue='k', 
                hue_order=k_range,
                palette='Set2')
    plt.title('Rouge-L Score Distribution by Model and k')
    plt.xticks(rotation=0)
    plt.ylabel('Rouge-L Score')
    plt.xlabel('Model')
    plt.legend(title='k')
    plt.tight_layout()
    plt.savefig(f'{output_dir}/score_distributions_boxplot.png')
    plt.close()
    
    # Violin plot
    plt.figure(figsize=(12, 6))
    sns.violinplot(data=df, x='model', y='score', hue='k',
                  hue_order=k_range,
                  palette='Set2')
    plt.title('Rouge-L Score Distribution (Violin Plot)')
    plt.xticks(rotation=0)
    plt.ylabel('Rouge-L Score')
    plt.xlabel('Model')
    plt.legend(title='k')
    plt.tight_layout()
    plt.savefig(f'{output_dir}/score_distributions_violin.png')
    plt.close()
    
    # Zero scores analysis
    plt.figure(figsize=(12, 6))
    zero_scores = df.groupby(['k', 'model'])['score'].apply(
        lambda x: (x == 0).mean() * 100
    ).reset_index()
    
    sns.barplot(data=zero_scores, x='model', y='score', hue='k',
                hue_order=k_range,
                palette='Set2')
    plt.title('Percentage of Zero Scores by Model and k')
    plt.xticks(rotation=0)
    plt.ylabel('Percentage of Zeros')
    plt.xlabel('Model')
    plt.legend(title='k')
    plt.tight_layout()
    plt.savefig(f'{output_dir}/zero_scores_analysis.png')
    plt.close()
    
    # Score distribution analysis
    bins = [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 1.0]
    bin_labels = ['0', '0-0.05', '0.05-0.1', '0.1-0.15', '0.15-0.2', '0.2-0.25', '0.25-0.3', '>0.3']
    
    # Create a function to bin scores with special handling for zeros
    def custom_bin(x):
        if x == 0:
            return '0'
        for i, (left, right) in enumerate(zip(bins[:-1], bins[1:])):
            if left <= x < right:
                return bin_labels[i+1]
        return bin_labels[-1]
    
    df['score_bin'] = df['score'].apply(custom_bin)
    df['score_bin'] = pd.Categorical(df['score_bin'], categories=bin_labels, ordered=True)
    
    dist_data = df.groupby(['model', 'k', 'score_bin']).size().reset_index(name='count')
    dist_data['percentage'] = dist_data.groupby(['model', 'k'])['count'].transform(lambda x: x / x.sum() * 100)
    
    # Create distribution plot for each k value
    for k_val in k_range:
        plt.figure(figsize=(14, 7))
        k_data = dist_data[dist_data['k'] == k_val]
        
        sns.barplot(data=k_data, x='score_bin', y='percentage', hue='model',
                   palette='Set2')
        plt.title(f'Score Distribution (k={k_val})', pad=20)
        plt.xticks(rotation=45)
        plt.ylabel('Percentage of Scores')
        plt.xlabel('Score Range')
        plt.legend(title='Model', bbox_to_anchor=(1.05, 1), loc='upper left')
        
        # Add a vertical line after the zero category
        plt.axvline(x=0.5, color='gray', linestyle='--', alpha=0.5)
        
        # Adjust layout to prevent label cutoff
        plt.tight_layout()
        plt.savefig(f'{output_dir}/score_distribution_k{k_val}.png', bbox_inches='tight', dpi=300)
        plt.close()

def create_model_comparison_plot(results, output_dir):
    
    # Define models to compare    
    # Set up the figure with two rows and two columns
    fig = plt.figure(figsize=(15, 12))
    
    # Define score ranges for distribution plots
    bins = [0, 0.000001, 0.05, 0.10, 0.15, 0.20, 0.30, 1.00]
    bin_labels = ['0', '0.01-0.05', '0.05-0.10', '0.10-0.15', '0.15-0.20', '0.20-0.30', '0.30-1.00']
    
    # Colors for k=0 and k=10
    colors = ['#1f77b4', '#ff7f0e']

    max_k = [r for r in results.keys() if r != "0"][0]    
    models_to_compare = list(results['0'].keys())
    
    # Process each model
    for idx, model in enumerate(models_to_compare):

        scores_k0 = np.array(results['0'].get(model, []))
        scores_maxk = np.array(results[max_k].get(model, []))
        
        ax = fig.add_subplot(2, 2, idx + 1)
        
        hist_k0, _ = np.histogram(scores_k0, bins=bins)
        hist_maxk, _ = np.histogram(scores_maxk, bins=bins)
        
        hist_k0 = hist_k0 / len(scores_k0) * 100
        hist_maxk = hist_maxk / len(scores_maxk) * 100
        
        x = np.arange(len(bin_labels))
        width = 0.35
        ax.bar(x - width/2, hist_k0, width, label='k=0', color=colors[0])
        ax.bar(x + width/2, hist_maxk, width, label=f'k={max_k}', color=colors[1])
        
        ax.set_title(f'{model}\nScore Distribution', pad=10)
        ax.set_xlabel('Score Range')
        ax.set_ylabel('Percentage of Samples')
        ax.set_xticks(x)
        ax.set_xticklabels(bin_labels, rotation=45)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Set y-axis limit to be consistent across all plots
        ax.set_ylim(0, 100)
    
    # Add overall title and adjust layout
    plt.suptitle('Model Comparison: Score Distributions', fontsize=16, y=1.02)
    plt.tight_layout()
    
    # Save the plot
    plt.savefig(os.path.join(output_dir, 'model_comparison_detailed.png'), 
                bbox_inches='tight', dpi=300)
    plt.close()

def plot_score_changes(results, output_dir):

    models = list(results['0'].keys())
    max_k = [r for r in results.keys() if r != "0"][0]   
    increased = []
    decreased = []
    
    for model in models:
        k0_scores = np.array(results['0'][model])
        kmax_scores = np.array(results[max_k][model])
        
        # Calculate differences
        diff = kmax_scores - k0_scores
        
        # Separate increases and decreases
        increases = diff[diff > 0]
        decreases = diff[diff < 0]
        
        increased.append(np.sum(diff > 0))
        decreased.append(np.sum(diff < 0))
    
    # Prepare data for plotting
    x = np.arange(len(models))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(10, 6))
    rects1 = ax.bar(x - width/2, increased, width, label='Increased', color='green', alpha=0.6)
    rects2 = ax.bar(x + width/2, decreased, width, label='Decreased', color='red', alpha=0.6)
    
    # Customize plot
    ax.set_ylabel('Number of Samples')
    ax.set_title(f'Changes in ROUGE Scores (k=0 to k={max_k})')
    ax.set_xticks(x)
    ax.set_xticklabels([create_model_display_name(model) for model in models])
    ax.legend()
    
    # Add value labels on bars
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{int(height)}',
                       xy=(rect.get_x() + rect.get_width()/2, height),
                       xytext=(0, 3),
                       textcoords="offset points",
                       ha='center', va='bottom')
    
    autolabel(rects1)
    autolabel(rects2)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'rouge_score_changes.png'))
    plt.close()

def analyze_score_change_statistics(results, output_dir):
    """
    Analyze detailed statistics about how ROUGE scores change when k increases from 0 to 10.
    Saves results to a CSV file and returns a DataFrame with the statistics.
    """
    stats_data = []
    max_k = [r for r in results.keys() if r != "0"][0]   
    
    for model in results['0'].keys():
        k0_scores = np.array(results['0'][model])
        kmax_scores = np.array(results[max_k][model])
        
        # Calculate differences
        diff = kmax_scores - k0_scores
        
        # Separate increases and decreases
        increases = diff[diff > 0]
        decreases = diff[diff < 0]
        
        stats = {
            'Model': model,
            'Total_Samples': len(diff),
            'Increased_Count': len(increases),
            'Decreased_Count': len(decreases),
            'No_Change_Count': np.sum(diff == 0),
            'Mean_Increase': np.mean(increases) if len(increases) > 0 else 0,
            'Mean_Decrease': np.mean(decreases) if len(decreases) > 0 else 0,
            'Median_Increase': np.median(increases) if len(increases) > 0 else 0,
            'Median_Decrease': np.median(decreases) if len(decreases) > 0 else 0,
            'Max_Increase': np.max(increases) if len(increases) > 0 else 0,
            'Max_Decrease': np.min(decreases) if len(decreases) > 0 else 0,
        }
        
        # Add percentiles for increases
        if len(increases) > 0:
            increase_percentiles = np.percentile(increases, [25, 75, 90])
            stats.update({
                'Increase_25th_Percentile': increase_percentiles[0],
                'Increase_75th_Percentile': increase_percentiles[1],
                'Increase_90th_Percentile': increase_percentiles[2],
            })
        else:
            stats.update({
                'Increase_25th_Percentile': 0,
                'Increase_75th_Percentile': 0,
                'Increase_90th_Percentile': 0,
            })
            
        # Add percentiles for decreases
        if len(decreases) > 0:
            decrease_percentiles = np.percentile(decreases, [10, 25, 75])
            stats.update({
                'Decrease_10th_Percentile': decrease_percentiles[0],
                'Decrease_25th_Percentile': decrease_percentiles[1],
                'Decrease_75th_Percentile': decrease_percentiles[2],
            })
        else:
            stats.update({
                'Decrease_10th_Percentile': 0,
                'Decrease_25th_Percentile': 0,
                'Decrease_75th_Percentile': 0,
            })
        
        stats_data.append(stats)
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(stats_data)
    csv_path = os.path.join(output_dir, 'rouge_score_change_statistics.csv')
    df.to_csv(csv_path, index=False, float_format='%.4f')
    
    # Print summary to console
    print(f"\nROUGE Score Change Statistics (k=0 to k={max_k}):")
    print("=" * 80)
    for _, row in df.iterrows():
        model_name = create_model_display_name(row['Model']).replace('\n', ' ')
        print(f"\nModel: {model_name}")
        print(f"Total Samples: {int(row['Total_Samples'])}")
        print(f"Improved: {int(row['Increased_Count'])} samples (Mean: {row['Mean_Increase']:.4f}, Median: {row['Median_Increase']:.4f})")
        print(f"Decreased: {int(row['Decreased_Count'])} samples (Mean: {row['Mean_Decrease']:.4f}, Median: {row['Median_Decrease']:.4f})")
        print(f"No Change: {int(row['No_Change_Count'])} samples")
    
    return df

def main():
    args = get_args()
    dataset = parse_dataset(args.dataset)
    
    # Ensure absolute paths
    visuals_dir = os.path.join('personality_analysis', 'files', 'visuals', dataset.tag)
    csvs_dir = os.path.join('personality_analysis', 'files', 'csv', dataset.tag)

    os.makedirs(visuals_dir, exist_ok=True)
    os.makedirs(csvs_dir, exist_ok=True)
    
    # Construct input file path with absolute path
    input_file = os.path.join('evaluation', 'files', 'indv', f'eval_{dataset.tag}.json')
    
    k_range =  ["0", "10"]
    filtered_data = load_and_filter_data(input_file, k_range)
    print(f"Loaded {len(filtered_data)} filtered experiments")
    
    results = analyze_scores(filtered_data, k_range)
    
    # Generate all analyses and plots
    analyze_score_transitions(results, csvs_dir)
    plot_comparisons(results, visuals_dir, k_range)
    create_model_comparison_plot(results, visuals_dir)
    plot_score_changes(results, visuals_dir)
    analyze_score_change_statistics(results, csvs_dir) 

if __name__ == "__main__":
    main()
