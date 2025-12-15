import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { MicroserviceOptions, Transport } from '@nestjs/microservices';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // Start MQTT Microservice
  // app.connectMicroservice<MicroserviceOptions>({
  //   transport: Transport.MQTT,
  //   options: {
  //     url: 'mqtt://localhost:1883',
  //   },
  // });

  // await app.startAllMicroservices();

  app.enableCors({
    origin: "*",
    methods: "GET,POST,PUT,PATCH,DELETE,OPTIONS",
    allowedHeaders: "Content-Type, Authorization",
  });

  await app.listen(3001);

  console.log('HTTP + MQTT services started');
}
bootstrap();
