import os
import torch
from torch.optim import AdamW
from torch.utils.tensorboard import SummaryWriter
from torch.utils.data import DataLoader
from transformers import Trainer, TrainingArguments, AutoFeatureExtractor, AutoModelForSequenceClassification, WavLMForSequenceClassification, HubertForSequenceClassification, Wav2Vec2ForSequenceClassification,WhisperForAudioClassification
import evaluate
import argparse
from module.mydatasets import *
from module.dataConstant import SEX, LABELS, SPEAKER_NUM

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", type=str, default="microsoft/wavlm-base", help="The path or name of the pre-trained model")
    parser.add_argument("--manifest_path", type=str, default="./data", help="The path of the manifest file")
    parser.add_argument("--dataset_path", type=str, default="/root/DialectDataset/Datatang-Dialect", help="The path of the dataset")
    parser.add_argument("--model_name", type=str, default="wavlm-base-dialect", help="The name of your trained model")
    parser.add_argument("--num_eopch", type=int, default=5, help="The number of training epochs")
    parser.add_argument("--gradient_accumulation_steps", type=int, default=2, help="The number of gradient accumulation steps")
    parser.add_argument("--lr", type=float, default=2e-5, help="The learning rate of the optimizer")
    parser.add_argument("--freeze_feature_encoder", action="store_true", help="Whether to freeze the feature encoder")
    return parser.parse_args()

# 评估指标
acc_metric = evaluate.load("./metrics/accuracy")
# f1_metric = evaluate.load("./metrics/f1")
# re_metric = evaluate.load("./metrics/recall")
def eval_metric(eval_predict):
    predictions, labels = eval_predict
    predictions = predictions.argmax(axis=-1)
    accuracy = acc_metric.compute(predictions=predictions, references=labels)
    # f1 = f1_metric.compute(predictions=predictions, references=labels)
    # recall = re_metric.compute(predictions=predictions, references=labels)
    return {
        "accuracy": accuracy["accuracy"],
        # "f1": f1["f1"],
        # "recall": recall["recall"]
    }

def collate_fn(batch):
    """
    batch -> speech_feature, input_lengths, label, sex, speaker
    Return:
        inputs : [batch, max_time, dim]
        input_lengths: [batch]
        label: [batch]
        sex: [batch]
        speaker: [batch]
    """
    speech_feature = [i[0].numpy() for i in batch]
    label = torch.LongTensor([i[1] for i in batch])

    # TODO add FBANK and MFCC feature

    speech_feature = feature_extractor(
        speech_feature, 
        sampling_rate=feature_extractor.sampling_rate,
        padding=True,
        return_tensors="pt"
    )["input_values"]

    return {
            "input_values": speech_feature,
            "labels": label,
        }

def main(args):
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    model.to(device)

    train_dataset = MyDataset(
        manifest_path=os.path.join(manifest_path,"train.tsv"), dataset_path=dataset_path, speed_perturb=True)

    dev_dataset = MyDataset(
        manifest_path=os.path.join(manifest_path,"dev.tsv"), dataset_path=dataset_path)

    train_args = TrainingArguments(output_dir=output_dir, 
                                auto_find_batch_size="power2",
                                logging_steps=10,
                                evaluation_strategy="epoch",
                                num_train_epochs = args.num_eopch,
                                gradient_accumulation_steps=args.gradient_accumulation_steps,
                                learning_rate=args.lr,
                                save_strategy="epoch",
                                save_total_limit=1,
                                weight_decay=0.01,
                                metric_for_best_model="accuracy",
                                load_best_model_at_end=True
                                )
    
    # TODO add coustom optimizers for Trainer
    trainer = Trainer(model = model, 
                    args = train_args,
                    train_dataset = train_dataset,
                    eval_dataset = dev_dataset,
                    data_collator=collate_fn,
                    compute_metrics = eval_metric)
    print("Start training...")
    trainer.train()
    print("Start evaluating...")
    trainer.evaluate(eval_dataset=dev_dataset)
    print("All done!")

if __name__ == "__main__":
    args = get_args()
    model_path = args.model_path
    manifest_path = args.manifest_path
    dataset_path = args.dataset_path
    model_name = args.model_name
    output_dir = os.path.join("./exp", model_name)

    feature_extractor = AutoFeatureExtractor.from_pretrained(model_path)
    if model_path.startswith("microsoft/wavlm"):
        model = WavLMForSequenceClassification.from_pretrained(model_path, num_labels=len(LABELS))
    elif model_path.startswith("facebook/wav2vec2"):
        model = Wav2Vec2ForSequenceClassification.from_pretrained(model_path, num_labels=len(LABELS))
    elif model_path.startswith("facebook/hubert"):
        model = HubertForSequenceClassification.from_pretrained(model_path, num_labels=len(LABELS))
    elif model_path.startswith("openai/whisper"):
        model = WhisperForAudioClassification.from_pretrained(model_path, num_labels=len(LABELS))
    else:
        model = AutoModelForSequenceClassification.from_pretrained(model_path, num_labels=len(LABELS)) 
    
    if args.freeze_feature_encoder:
        model.freeze_feature_encoder()

    main(args)