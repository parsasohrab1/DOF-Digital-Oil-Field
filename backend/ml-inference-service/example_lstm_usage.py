"""
مثال استفاده از مدل LSTM برای پیش‌بینی سری‌های زمانی

این فایل نشان می‌دهد چگونه می‌توان از مدل LSTM برای پیش‌بینی مقادیر آینده استفاده کرد.
"""

import numpy as np
import sys
import os

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))

from mlflow_integration import get_mlflow_manager


def generate_sample_time_series_data(length: int = 2000) -> np.ndarray:
    """
    تولید داده نمونه برای آموزش مدل

    Args:
        length: طول سری زمانی

    Returns:
        آرایه numpy با شکل (length, 1)
    """
    np.random.seed(42)
    t = np.arange(0, length, 0.1)
    # ترکیب چند موج سینوسی با نویز
    data = (
        np.sin(0.1 * t)
        + 0.5 * np.sin(0.3 * t)
        + 0.3 * np.sin(0.5 * t)
        + np.random.normal(0, 0.1, len(t))
    )
    return data.reshape(-1, 1)


def example_train_and_predict():
    """مثال کامل: آموزش مدل و پیش‌بینی"""

    print("=" * 60)
    print("مثال استفاده از مدل LSTM برای پیش‌بینی سری‌های زمانی")
    print("=" * 60)

    # 1. ایجاد MLflow Manager
    print("\n1. ایجاد MLflow Manager...")
    manager = get_mlflow_manager(model_path="./models", tracking_uri="file:./mlruns")

    # 2. تولید داده نمونه
    print("\n2. تولید داده نمونه برای آموزش...")
    training_data = generate_sample_time_series_data(length=2000)
    print(f"   تعداد نقاط داده: {len(training_data)}")

    # 3. آموزش مدل
    print("\n3. آموزش مدل LSTM...")
    print("   این مرحله ممکن است چند دقیقه طول بکشد...")
    manager.train_time_series_model(
        time_series_data=training_data,
        seq_length=60,  # استفاده از 60 نقطه قبلی
        forecast_horizon=1,  # پیش‌بینی 1 گام آینده
        epochs=30,  # 30 دوره آموزش (برای مثال سریع)
        batch_size=32,
        validation_split=0.2,
    )
    print("   ✓ مدل با موفقیت آموزش داده شد!")

    # 4. تولید داده تاریخی برای پیش‌بینی
    print("\n4. آماده‌سازی داده تاریخی برای پیش‌بینی...")
    # استفاده از آخرین 100 نقطه از داده آموزشی
    historical_data = training_data[-100:].flatten().tolist()
    print(f"   تعداد نقاط تاریخی: {len(historical_data)}")

    # 5. انجام پیش‌بینی
    print("\n5. انجام پیش‌بینی...")
    result = manager.predict_time_series(
        historical_data=historical_data, forecast_steps=10  # پیش‌بینی 10 گام آینده
    )

    print("\n" + "=" * 60)
    print("نتایج پیش‌بینی:")
    print("=" * 60)
    print(f"تعداد گام‌های پیش‌بینی: {result['forecast_steps']}")
    print(f"طول دنباله ورودی: {result['sequence_length']}")
    print(f"سطح اطمینان: {result['confidence']:.2%}")
    print("\nمقادیر پیش‌بینی شده:")
    for i, pred in enumerate(result["predictions"], 1):
        print(f"  گام {i}: {pred:.4f}")

    print("\n" + "=" * 60)
    print("✓ مثال با موفقیت اجرا شد!")
    print("=" * 60)


def example_load_and_predict():
    """مثال: بارگذاری مدل از MLflow و پیش‌بینی"""

    print("\n" + "=" * 60)
    print("مثال: بارگذاری مدل از MLflow")
    print("=" * 60)

    # 1. ایجاد Manager
    manager = get_mlflow_manager(model_path="./models", tracking_uri="file:./mlruns")

    # 2. بارگذاری مدل
    print("\nبارگذاری مدل از MLflow...")
    model = manager.load_model("time-series-forecast")

    if model is None:
        print("❌ مدل یافت نشد. لطفاً ابتدا مدل را آموزش دهید.")
        return

    print("✓ مدل با موفقیت بارگذاری شد!")

    # 3. تولید داده نمونه برای پیش‌بینی
    print("\nتولید داده تاریخی نمونه...")
    # تولید یک سری زمانی ساده
    historical_data = [np.sin(i * 0.1) + np.random.normal(0, 0.1) for i in range(100)]

    # 4. پیش‌بینی
    print("انجام پیش‌بینی...")
    result = manager.predict_time_series(
        historical_data=historical_data, forecast_steps=5
    )

    print(f"\nمقادیر پیش‌بینی شده: {result['predictions']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="مثال استفاده از مدل LSTM")
    parser.add_argument(
        "--mode",
        choices=["train", "predict", "both"],
        default="both",
        help="حالت اجرا: train (آموزش), predict (پیش‌بینی), both (هر دو)",
    )

    args = parser.parse_args()

    if args.mode in ["train", "both"]:
        example_train_and_predict()

    if args.mode in ["predict", "both"]:
        example_load_and_predict()
