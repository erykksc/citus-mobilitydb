#!/bin/bash

# Detect current tmux session, or default to "citus-mobility"
if [ -n "$TMUX" ]; then
  # Extract session name from TMUX environment variable
  SESSION=$(tmux display-message -p '#S')
else
  SESSION="citus-mobility"
  # Start new tmux session (detached)
  tmux new-session -d -s $SESSION
fi

# Rename current window to "monitor" (create if it doesn't exist)
tmux new-window -t $SESSION -n monitor

# Split window horizontally into 4 panes
tmux split-window -v -t $SESSION:monitor
tmux split-window -v -t $SESSION:monitor
tmux split-window -v -t $SESSION:monitor

# Send commands to each pane
tmux select-pane -t $SESSION:monitor.0
tmux send-keys "watch minikube ip" C-m

tmux select-pane -t $SESSION:monitor.1
tmux send-keys "watch kubectl get service" C-m

tmux select-pane -t $SESSION:monitor.2
tmux send-keys "watch kubectl get pods" C-m

tmux select-pane -t $SESSION:monitor.3
tmux send-keys "PGPASSWORD='postgres' watch \"psql -h $CLUSTERIP -p 32345 -U postgres -d postgres -c 'SELECT * FROM pg_dist_node;'\"" C-m

# Only attach if we created the session
if [ "$SESSION" = "citus-mobility" ]; then
  tmux attach-session -t $SESSION
else
  echo "Commands sent to existing tmux session: $SESSION"
fi

