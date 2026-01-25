import torch
import torch.nn as nn

class LSTMModel(nn.Module):
    def __init__(self, input_dim, hidden_dim, num_layers, output_dim):
        super(LSTMModel, self).__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        # Capa LSTM
        # batch_first=True espera inputs de forma (batch_size, seq_length, input_dim)
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2)
        
        # Capa totalmente conectada para predecir
        self.fc = nn.Linear(hidden_dim, output_dim)
        
        # Función de activación final (Sigmoid para probabilidad binomial)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        # Inicializar hidden state y cell state
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
        
        # Forward propagate LSTM
        out, _ = self.lstm(x, (h0, c0))
        
        # Decodificar el estado oculto del último paso de tiempo
        out = self.fc(out[:, -1, :])
        
        return out
